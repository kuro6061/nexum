use std::collections::HashMap;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use anyhow::Result;
use serde_json::Value;
use tokio::sync::RwLock;
use tonic::{transport::Server, Request, Response, Status};
use opentelemetry::trace::TracerProvider as _;
use tracing_subscriber::util::SubscriberInitExt;
use chrono::Utc;
use uuid::Uuid;

pub mod nexum_proto {
    tonic::include_proto!("nexum");
}

use nexum_proto::nexum_service_server::{NexumService, NexumServiceServer};
use nexum_proto::*;

const TASK_TIMEOUT_SECS: i64 = 60;
const CLAIM_CHECK_THRESHOLD: usize = 100 * 1024; // 100KB

struct Metrics {
    executions_started: AtomicU64,
    executions_completed: AtomicU64,
    executions_failed: AtomicU64,
    tasks_completed: AtomicU64,
    tasks_failed: AtomicU64,
    tasks_retried: AtomicU64,
}

impl Metrics {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            executions_started: AtomicU64::new(0),
            executions_completed: AtomicU64::new(0),
            executions_failed: AtomicU64::new(0),
            tasks_completed: AtomicU64::new(0),
            tasks_failed: AtomicU64::new(0),
            tasks_retried: AtomicU64::new(0),
        })
    }

    fn prometheus_text(&self) -> String {
        format!(
"# HELP nexum_executions_started_total Total workflow executions started
# TYPE nexum_executions_started_total counter
nexum_executions_started_total {}
# HELP nexum_executions_completed_total Total workflow executions completed
# TYPE nexum_executions_completed_total counter
nexum_executions_completed_total {}
# HELP nexum_executions_failed_total Total workflow executions failed
# TYPE nexum_executions_failed_total counter
nexum_executions_failed_total {}
# HELP nexum_tasks_completed_total Total tasks completed
# TYPE nexum_tasks_completed_total counter
nexum_tasks_completed_total {}
# HELP nexum_tasks_failed_total Total tasks failed (including retries)
# TYPE nexum_tasks_failed_total counter
nexum_tasks_failed_total {}
# HELP nexum_tasks_retried_total Total task retries
# TYPE nexum_tasks_retried_total counter
nexum_tasks_retried_total {}
",
            self.executions_started.load(Ordering::Relaxed),
            self.executions_completed.load(Ordering::Relaxed),
            self.executions_failed.load(Ordering::Relaxed),
            self.tasks_completed.load(Ordering::Relaxed),
            self.tasks_failed.load(Ordering::Relaxed),
            self.tasks_retried.load(Ordering::Relaxed),
        )
    }
}

fn get_database_url() -> String {
    std::env::var("DATABASE_URL").unwrap_or_else(|_| {
        let dir = std::path::Path::new(".nexum");
        std::fs::create_dir_all(dir).ok();
        "sqlite://.nexum/local.db?mode=rwc".to_string()
    })
}

fn is_postgres(database_url: &str) -> bool {
    database_url.starts_with("postgres://") || database_url.starts_with("postgresql://")
}

struct NexumServer {
    db: sqlx::AnyPool,
    is_postgres: bool,
    registry: Arc<RwLock<HashMap<String, Value>>>,
    metrics: Arc<Metrics>,
}

impl NexumServer {
    async fn new() -> Result<Self> {
        let database_url = get_database_url();
        let pg = is_postgres(&database_url);

        let db = sqlx::AnyPool::connect(&database_url).await?;

        if pg {
            Self::run_postgres_migrations(&db).await?;
        } else {
            Self::run_sqlite_migrations(&db).await?;
        }

        // Load all registered workflow versions from DB into registry
        let versions: Vec<(String, String, String)> = sqlx::query_as(
            "SELECT workflow_id, version_hash, ir_json FROM workflow_versions"
        )
        .fetch_all(&db)
        .await?;

        let mut registry_map = HashMap::new();
        for (workflow_id, version_hash, ir_json) in &versions {
            if let Ok(ir) = serde_json::from_str::<Value>(ir_json) {
                let key = format!("{}:{}", workflow_id, version_hash);
                registry_map.insert(key, ir);
            }
        }

        let db_type = if pg { "PostgreSQL" } else { "SQLite" };
        tracing::info!(count = versions.len(), db = db_type, "Loaded workflow versions from DB");

        Ok(Self {
            db,
            is_postgres: pg,
            registry: Arc::new(RwLock::new(registry_map)),
            metrics: Metrics::new(),
        })
    }

    async fn run_sqlite_migrations(db: &sqlx::AnyPool) -> Result<()> {
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS workflow_executions (
                execution_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'RUNNING',
                input_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                parent_execution_id TEXT,
                parent_node_id TEXT
            )",
        )
        .execute(db)
        .await?;

        // Migration: add parent columns if missing (for pre-existing databases)
        let exec_columns: Vec<(i64, String, String, i64, Option<String>, i64)> =
            sqlx::query_as("PRAGMA table_info(workflow_executions)")
                .fetch_all(db)
                .await?;
        let has_parent_execution_id = exec_columns.iter().any(|c| c.1 == "parent_execution_id");
        if !has_parent_execution_id {
            sqlx::query("ALTER TABLE workflow_executions ADD COLUMN parent_execution_id TEXT")
                .execute(db).await?;
            sqlx::query("ALTER TABLE workflow_executions ADD COLUMN parent_node_id TEXT")
                .execute(db).await?;
        }

        sqlx::query(
            "CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                sequence_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(execution_id, sequence_id)
            )",
        )
        .execute(db)
        .await?;

        sqlx::query(
            "CREATE TABLE IF NOT EXISTS task_queue (
                task_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                input_json TEXT,
                idempotency_key TEXT,
                status TEXT NOT NULL DEFAULT 'READY',
                locked_by TEXT,
                locked_at TEXT,
                retry_count INTEGER DEFAULT 0,
                scheduled_at TEXT DEFAULT (datetime('now')),
                approval_status TEXT,
                approver TEXT,
                approval_comment TEXT,
                sub_execution_id TEXT,
                sub_workflow_id TEXT,
                sub_input_json TEXT,
                map_item_json TEXT,
                map_index INTEGER,
                map_total INTEGER,
                map_parent_node_id TEXT,
                node_type TEXT
            )",
        )
        .execute(db)
        .await?;

        // Migration: add columns if missing (for pre-existing databases)
        let columns: Vec<(i64, String, String, i64, Option<String>, i64)> =
            sqlx::query_as("PRAGMA table_info(task_queue)")
                .fetch_all(db)
                .await?;
        let has_locked_at = columns.iter().any(|c| c.1 == "locked_at");
        if !has_locked_at {
            sqlx::query("ALTER TABLE task_queue ADD COLUMN locked_at TEXT")
                .execute(db).await?;
        }
        let has_approval_status = columns.iter().any(|c| c.1 == "approval_status");
        if !has_approval_status {
            sqlx::query("ALTER TABLE task_queue ADD COLUMN approval_status TEXT").execute(db).await?;
            sqlx::query("ALTER TABLE task_queue ADD COLUMN approver TEXT").execute(db).await?;
            sqlx::query("ALTER TABLE task_queue ADD COLUMN approval_comment TEXT").execute(db).await?;
        }
        let has_sub_execution_id = columns.iter().any(|c| c.1 == "sub_execution_id");
        if !has_sub_execution_id {
            sqlx::query("ALTER TABLE task_queue ADD COLUMN sub_execution_id TEXT").execute(db).await?;
            sqlx::query("ALTER TABLE task_queue ADD COLUMN sub_workflow_id TEXT").execute(db).await?;
            sqlx::query("ALTER TABLE task_queue ADD COLUMN sub_input_json TEXT").execute(db).await?;
        }
        let has_map_item_json = columns.iter().any(|c| c.1 == "map_item_json");
        if !has_map_item_json {
            sqlx::query("ALTER TABLE task_queue ADD COLUMN map_item_json TEXT").execute(db).await?;
            sqlx::query("ALTER TABLE task_queue ADD COLUMN map_index INTEGER").execute(db).await?;
            sqlx::query("ALTER TABLE task_queue ADD COLUMN map_total INTEGER").execute(db).await?;
            sqlx::query("ALTER TABLE task_queue ADD COLUMN map_parent_node_id TEXT").execute(db).await?;
            sqlx::query("ALTER TABLE task_queue ADD COLUMN node_type TEXT").execute(db).await?;
        }

        sqlx::query(
            "CREATE TABLE IF NOT EXISTS workflow_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                ir_json TEXT NOT NULL,
                compatibility TEXT NOT NULL DEFAULT 'UNKNOWN',
                registered_at TEXT DEFAULT (datetime('now')),
                UNIQUE(workflow_id, version_hash)
            )",
        )
        .execute(db)
        .await?;

        sqlx::query(
            "CREATE TABLE IF NOT EXISTS map_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                map_node_id TEXT NOT NULL,
                item_index INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                UNIQUE(execution_id, map_node_id, item_index)
            )",
        )
        .execute(db)
        .await?;

        Ok(())
    }

    async fn run_postgres_migrations(db: &sqlx::AnyPool) -> Result<()> {
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS workflow_executions (
                execution_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'RUNNING',
                input_json TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                parent_execution_id TEXT,
                parent_node_id TEXT
            )"
        ).execute(db).await?;

        sqlx::query(
            "CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                execution_id TEXT NOT NULL,
                sequence_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )"
        ).execute(db).await?;

        sqlx::query(
            "CREATE TABLE IF NOT EXISTS task_queue (
                task_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL DEFAULT 'EFFECT',
                version_hash TEXT,
                input_json TEXT,
                idempotency_key TEXT,
                status TEXT NOT NULL DEFAULT 'READY',
                scheduled_at TIMESTAMPTZ DEFAULT NOW(),
                locked_by TEXT,
                locked_at TIMESTAMPTZ,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                output_json TEXT,
                error TEXT,
                approval_status TEXT,
                approver TEXT,
                approval_comment TEXT,
                map_item_json TEXT,
                map_index INTEGER,
                map_total INTEGER,
                map_parent_node_id TEXT,
                sub_execution_id TEXT,
                sub_workflow_id TEXT,
                sub_input_json TEXT
            )"
        ).execute(db).await?;

        sqlx::query(
            "CREATE TABLE IF NOT EXISTS workflow_versions (
                id BIGSERIAL PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                ir_json TEXT NOT NULL,
                compatibility TEXT NOT NULL DEFAULT 'NEW',
                registered_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(workflow_id, version_hash)
            )"
        ).execute(db).await?;

        sqlx::query(
            "CREATE TABLE IF NOT EXISTS map_results (
                id BIGSERIAL PRIMARY KEY,
                execution_id TEXT NOT NULL,
                map_node_id TEXT NOT NULL,
                item_index INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                UNIQUE(execution_id, map_node_id, item_index)
            )"
        ).execute(db).await?;

        // Indexes for performance
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status)").execute(db).await?;
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_task_queue_execution ON task_queue(execution_id)").execute(db).await?;
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_events_execution ON events(execution_id)").execute(db).await?;
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_executions_status ON workflow_executions(status)").execute(db).await?;

        Ok(())
    }

    /// SQL for current timestamp: datetime('now') on SQLite, NOW() on PostgreSQL
    fn now_sql(&self) -> &str {
        if self.is_postgres { "NOW()" } else { "datetime('now')" }
    }

    async fn get_next_sequence_id(&self, execution_id: &str) -> Result<i64, Status> {
        let row: (i64,) =
            sqlx::query_as("SELECT COALESCE(MAX(sequence_id), 0) + 1 FROM events WHERE execution_id = ?")
                .bind(execution_id)
                .fetch_one(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;
        Ok(row.0)
    }

    async fn get_completed_nodes(&self, execution_id: &str) -> Result<Vec<String>, Status> {
        // Fetch all NodeCompleted payloads and extract node_id in Rust (cross-DB compatible)
        let rows: Vec<(String,)> = sqlx::query_as(
            "SELECT payload FROM events WHERE execution_id = ? AND event_type = 'NodeCompleted'"
        )
        .bind(execution_id)
        .fetch_all(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        let mut nodes = Vec::new();
        for (payload_str,) in rows {
            if let Ok(v) = serde_json::from_str::<Value>(&payload_str) {
                if let Some(node_id) = v.get("node_id").and_then(|n| n.as_str()) {
                    nodes.push(node_id.to_string());
                }
            }
        }
        Ok(nodes)
    }

    async fn get_scheduled_nodes(&self, execution_id: &str) -> Result<Vec<String>, Status> {
        let rows: Vec<(String,)> = sqlx::query_as(
            "SELECT node_id FROM task_queue WHERE execution_id = ?"
        )
        .bind(execution_id)
        .fetch_all(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        Ok(rows.into_iter().map(|r| r.0).collect())
    }

    /// Find a NodeCompleted event for a specific node_id (cross-DB: parses JSON in Rust)
    async fn find_node_completed_event(&self, execution_id: &str, node_id: &str) -> Result<Option<String>, Status> {
        let rows: Vec<(String,)> = sqlx::query_as(
            "SELECT payload FROM events WHERE execution_id = ? AND event_type = 'NodeCompleted'"
        )
        .bind(execution_id)
        .fetch_all(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        for (payload_str,) in rows {
            if let Ok(v) = serde_json::from_str::<Value>(&payload_str) {
                if v.get("node_id").and_then(|n| n.as_str()) == Some(node_id) {
                    return Ok(Some(payload_str));
                }
            }
        }
        Ok(None)
    }

    async fn schedule_ready_nodes(
        &self,
        execution_id: &str,
        workflow_id: &str,
        version_hash: &str,
    ) -> Result<(), Status> {
        let registry = self.registry.read().await;
        let key = format!("{}:{}", workflow_id, version_hash);
        let ir = registry
            .get(&key)
            .ok_or_else(|| Status::not_found("Workflow not registered"))?;

        let nodes = ir
            .get("nodes")
            .and_then(|n| n.as_object())
            .ok_or_else(|| Status::internal("Invalid IR: missing nodes"))?;

        let completed = self.get_completed_nodes(execution_id).await?;
        let scheduled = self.get_scheduled_nodes(execution_id).await?;

        // Compute set of nodes skipped by ROUTER decisions
        let mut skipped_nodes: std::collections::HashSet<String> = std::collections::HashSet::new();
        for (router_id, node_def) in nodes {
            if node_def.get("type").and_then(|t| t.as_str()) != Some("ROUTER") { continue; }
            if !completed.contains(router_id) { continue; }
            if let Some(p) = self.find_node_completed_event(execution_id, router_id).await? {
                if let Ok(payload) = serde_json::from_str::<Value>(&p) {
                    let routed_to = payload.get("output").and_then(|o| o.get("routed_to")).and_then(|r| r.as_str()).unwrap_or("");
                    if let Some(routes) = node_def.get("routes").and_then(|r| r.as_array()) {
                        for route in routes {
                            if let Some(target) = route.get("target").and_then(|t| t.as_str()) {
                                if target != routed_to { skipped_nodes.insert(target.to_string()); }
                            }
                        }
                    }
                }
            }
        }

        for (node_id, node_def) in nodes {
            if completed.contains(node_id) || scheduled.contains(node_id) || skipped_nodes.contains(node_id) {
                continue;
            }

            let deps = node_def
                .get("dependencies")
                .and_then(|d| d.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();

            // Consider ROUTER-skipped nodes as "completed" for dependency checking
            let all_deps_done = deps.iter().all(|dep| completed.contains(dep) || skipped_nodes.contains(dep));

            if all_deps_done {
                let task_id = format!("task-{}", Uuid::new_v4());
                let idempotency_key = format!("{}:{}:{}", execution_id, node_id, version_hash);

                let ir_node_type = node_def
                    .get("type")
                    .and_then(|t| t.as_str())
                    .unwrap_or("COMPUTE");

                // TIMER nodes: set scheduled_at in the future based on delay_seconds
                if ir_node_type == "TIMER" {
                    let delay_secs = node_def
                        .get("delay_seconds")
                        .and_then(|d| d.as_i64())
                        .unwrap_or(0);

                    let insert_sql = if self.is_postgres {
                        format!(
                            "INSERT INTO task_queue (task_id, execution_id, node_id, version_hash, idempotency_key, status, node_type, scheduled_at)
                             VALUES (?, ?, ?, ?, ?, 'READY', 'TIMER', NOW() + INTERVAL '{} seconds')",
                            delay_secs
                        )
                    } else {
                        "INSERT INTO task_queue (task_id, execution_id, node_id, version_hash, idempotency_key, status, node_type, scheduled_at)
                         VALUES (?, ?, ?, ?, ?, 'READY', 'TIMER', datetime('now', ? || ' seconds'))".to_string()
                    };

                    if self.is_postgres {
                        sqlx::query(&insert_sql)
                            .bind(&task_id)
                            .bind(execution_id)
                            .bind(node_id)
                            .bind(version_hash)
                            .bind(&idempotency_key)
                            .execute(&self.db)
                            .await
                            .map_err(|e| Status::internal(e.to_string()))?;
                    } else {
                        sqlx::query(&insert_sql)
                            .bind(&task_id)
                            .bind(execution_id)
                            .bind(node_id)
                            .bind(version_hash)
                            .bind(&idempotency_key)
                            .bind(format!("+{}", delay_secs))
                            .execute(&self.db)
                            .await
                            .map_err(|e| Status::internal(e.to_string()))?;
                    }

                    tracing::info!(
                        execution_id = execution_id,
                        node_id = node_id,
                        task_id = task_id,
                        delay_seconds = delay_secs,
                        "Scheduled TIMER task"
                    );
                } else {
                    sqlx::query(
                        "INSERT INTO task_queue (task_id, execution_id, node_id, version_hash, idempotency_key, status, node_type)
                         VALUES (?, ?, ?, ?, ?, 'READY', ?)"
                    )
                    .bind(&task_id)
                    .bind(execution_id)
                    .bind(node_id)
                    .bind(version_hash)
                    .bind(&idempotency_key)
                    .bind(ir_node_type)
                    .execute(&self.db)
                    .await
                    .map_err(|e| Status::internal(e.to_string()))?;

                    tracing::info!(
                        execution_id = execution_id,
                        node_id = node_id,
                        task_id = task_id,
                        node_type = ir_node_type,
                        "Scheduled task"
                    );
                }
            }
        }

        Ok(())
    }

    async fn check_execution_complete(
        &self,
        execution_id: &str,
        workflow_id: &str,
        version_hash: &str,
    ) -> Result<(), Status> {
        let registry = self.registry.read().await;
        let key = format!("{}:{}", workflow_id, version_hash);
        let ir = registry
            .get(&key)
            .ok_or_else(|| Status::not_found("Workflow not registered"))?;

        let nodes = ir
            .get("nodes")
            .and_then(|n| n.as_object())
            .ok_or_else(|| Status::internal("Invalid IR: missing nodes"))?;

        let completed = self.get_completed_nodes(execution_id).await?;

        // Build set of nodes that were NOT routed to by any ROUTER
        let mut skipped_nodes: std::collections::HashSet<String> = std::collections::HashSet::new();
        for (node_id, node_def) in nodes {
            if node_def.get("type").and_then(|t| t.as_str()) == Some("ROUTER") && completed.contains(node_id) {
                if let Some(payload_str) = self.find_node_completed_event(execution_id, node_id).await? {
                    if let Ok(payload) = serde_json::from_str::<Value>(&payload_str) {
                        let routed_to = payload.get("output")
                            .and_then(|o| o.get("routed_to"))
                            .and_then(|r| r.as_str())
                            .unwrap_or("");

                        if let Some(routes) = node_def.get("routes").and_then(|r| r.as_array()) {
                            for route in routes {
                                if let Some(target) = route.get("target").and_then(|t| t.as_str()) {
                                    if target != routed_to {
                                        skipped_nodes.insert(target.to_string());
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Check: all non-skipped nodes must be completed
        let all_done = nodes.keys().all(|node_id| {
            completed.contains(node_id) || skipped_nodes.contains(node_id)
        });

        if all_done {
            sqlx::query("UPDATE workflow_executions SET status = 'COMPLETED' WHERE execution_id = ?")
                .bind(execution_id)
                .execute(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;

            self.metrics.executions_completed.fetch_add(1, Ordering::Relaxed);
            tracing::info!(execution_id = %execution_id, "Execution completed");

            // Check if this was a child execution — trigger parent SUBWORKFLOW node
            let parent: Option<(Option<String>, Option<String>)> = sqlx::query_as(
                "SELECT parent_execution_id, parent_node_id FROM workflow_executions WHERE execution_id = ?"
            )
            .bind(execution_id)
            .fetch_optional(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

            if let Some((Some(parent_exec_id), Some(parent_node_id))) = parent {
                if !parent_exec_id.is_empty() {
                    let child_output = self.get_execution_final_output(execution_id).await?;

                    // Insert NodeCompleted event in parent
                    let event_id = format!("evt-{}", Uuid::new_v4());
                    let seq = self.get_next_sequence_id(&parent_exec_id).await?;
                    let payload = serde_json::json!({
                        "node_id": parent_node_id,
                        "output": child_output,
                    });
                    sqlx::query(
                        "INSERT INTO events (event_id, execution_id, sequence_id, event_type, payload)
                         VALUES (?, ?, ?, 'NodeCompleted', ?)"
                    )
                    .bind(&event_id)
                    .bind(&parent_exec_id)
                    .bind(seq)
                    .bind(serde_json::to_string(&payload).unwrap())
                    .execute(&self.db)
                    .await
                    .map_err(|e| Status::internal(e.to_string()))?;

                    // Mark SUBWORKFLOW task as DONE
                    sqlx::query(
                        "UPDATE task_queue SET status = 'DONE' WHERE execution_id = ? AND node_id = ? AND status = 'RUNNING'"
                    )
                    .bind(&parent_exec_id)
                    .bind(&parent_node_id)
                    .execute(&self.db)
                    .await
                    .map_err(|e| Status::internal(e.to_string()))?;

                    tracing::info!(
                        child_execution_id = %execution_id,
                        parent_execution_id = %parent_exec_id,
                        parent_node_id = %parent_node_id,
                        "Child completed, resuming parent SUBWORKFLOW"
                    );

                    // Continue parent workflow
                    let parent_row: (String, String) = sqlx::query_as(
                        "SELECT workflow_id, version_hash FROM workflow_executions WHERE execution_id = ?"
                    )
                    .bind(&parent_exec_id)
                    .fetch_one(&self.db)
                    .await
                    .map_err(|e| Status::internal(e.to_string()))?;

                    let (parent_wf_id, parent_version_hash) = parent_row;
                    self.schedule_ready_nodes(&parent_exec_id, &parent_wf_id, &parent_version_hash).await?;
                    Box::pin(self.check_execution_complete(&parent_exec_id, &parent_wf_id, &parent_version_hash)).await?;
                }
            }
        }

        Ok(())
    }

    async fn get_execution_final_output(&self, execution_id: &str) -> Result<serde_json::Value, Status> {
        let row: Option<(String,)> = sqlx::query_as(
            "SELECT payload FROM events
             WHERE execution_id = ? AND event_type = 'NodeCompleted'
             ORDER BY sequence_id DESC LIMIT 1"
        )
        .bind(execution_id)
        .fetch_optional(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        if let Some((payload,)) = row {
            let v: serde_json::Value = serde_json::from_str(&payload).unwrap_or_default();
            Ok(v.get("output").cloned().unwrap_or(serde_json::Value::Null))
        } else {
            Ok(serde_json::Value::Null)
        }
    }

    async fn store_payload(&self, execution_id: &str, node_id: &str, output_json: &str) -> Result<String, Status> {
        if output_json.len() <= CLAIM_CHECK_THRESHOLD {
            return Ok(output_json.to_string());
        }

        let blob_dir = std::path::Path::new(".nexum/blobs");
        if !blob_dir.exists() {
            std::fs::create_dir_all(blob_dir).map_err(|e| Status::internal(e.to_string()))?;
        }

        let blob_id = format!("{}-{}", execution_id, node_id);
        let blob_path = blob_dir.join(format!("{}.json", blob_id));
        tokio::fs::write(&blob_path, output_json).await
            .map_err(|e| Status::internal(format!("Failed to write blob: {}", e)))?;

        let pointer = serde_json::json!({
            "__nexum_claim_check__": true,
            "blob_id": blob_id,
            "size": output_json.len(),
            "path": blob_path.to_string_lossy()
        });
        Ok(serde_json::to_string(&pointer).unwrap())
    }

    async fn resolve_payload(&self, stored_json: &str) -> Result<String, Status> {
        let val: serde_json::Value = serde_json::from_str(stored_json)
            .map_err(|e| Status::internal(e.to_string()))?;

        if val.get("__nexum_claim_check__").and_then(|v| v.as_bool()).unwrap_or(false) {
            let path = val["path"].as_str().ok_or_else(|| Status::internal("Invalid claim check"))?;
            let content = tokio::fs::read_to_string(path).await
                .map_err(|e| Status::internal(format!("Failed to read blob: {}", e)))?;
            Ok(content)
        } else {
            Ok(stored_json.to_string())
        }
    }
}

// --- ROUTER condition evaluator ---

fn evaluate_condition(condition: &str, data: &serde_json::Value) -> bool {
    let condition = condition.trim();

    if let Some((path, op, expected)) = parse_condition(condition) {
        let actual = get_json_path(data, &path);
        match op.as_str() {
            "==" => json_equals(&actual, &expected),
            "!=" => !json_equals(&actual, &expected),
            ">" => json_gt(&actual, &expected),
            "<" => json_lt(&actual, &expected),
            ">=" => json_gte(&actual, &expected),
            "<=" => json_lte(&actual, &expected),
            _ => false,
        }
    } else if condition == "true" {
        true
    } else if condition == "false" {
        false
    } else {
        false
    }
}

fn parse_condition(condition: &str) -> Option<(String, String, String)> {
    for op in &[">=", "<=", "!=", "==", ">", "<"] {
        if let Some(pos) = condition.find(op) {
            let path = condition[..pos].trim().to_string();
            let value = condition[pos + op.len()..].trim().trim_matches('"').to_string();
            return Some((path, op.to_string(), value));
        }
    }
    None
}

fn get_json_path(data: &serde_json::Value, path: &str) -> serde_json::Value {
    let path = path.trim_start_matches("$.");
    let parts: Vec<&str> = path.split('.').collect();
    let mut current = data;
    for part in &parts {
        current = match current.get(*part) {
            Some(v) => v,
            None => return serde_json::Value::Null,
        };
    }
    current.clone()
}

fn json_equals(a: &serde_json::Value, b: &str) -> bool {
    match a {
        serde_json::Value::Bool(v) => (b == "true" && *v) || (b == "false" && !*v),
        serde_json::Value::Number(n) => n.to_string() == b,
        serde_json::Value::String(s) => s == b,
        _ => a.to_string() == b,
    }
}

fn json_gt(a: &serde_json::Value, b: &str) -> bool {
    let av = a.as_f64().unwrap_or(0.0);
    let bv: f64 = b.parse().unwrap_or(0.0);
    av > bv
}

fn json_lt(a: &serde_json::Value, b: &str) -> bool {
    let av = a.as_f64().unwrap_or(0.0);
    let bv: f64 = b.parse().unwrap_or(0.0);
    av < bv
}

fn json_gte(a: &serde_json::Value, b: &str) -> bool { !json_lt(a, b) }
fn json_lte(a: &serde_json::Value, b: &str) -> bool { !json_gt(a, b) }

fn analyze_compatibility(old_ir: &Value, new_ir: &Value) -> &'static str {
    let old_nodes = old_ir.get("nodes").and_then(|n| n.as_object());
    let new_nodes = new_ir.get("nodes").and_then(|n| n.as_object());

    match (old_nodes, new_nodes) {
        (Some(old), Some(new)) => {
            for (node_id, old_def) in old {
                match new.get(node_id) {
                    None => return "BREAKING",
                    Some(new_def) => {
                        if old_def.get("dependencies") != new_def.get("dependencies") {
                            return "BREAKING";
                        }
                        if old_def.get("type") != new_def.get("type") {
                            return "BREAKING";
                        }
                    }
                }
            }
            if new.len() > old.len() { "SAFE" } else { "IDENTICAL" }
        }
        _ => "BREAKING",
    }
}

#[tonic::async_trait]
impl NexumService for NexumServer {
    async fn register_workflow(
        &self,
        request: Request<WorkflowIr>,
    ) -> Result<Response<AckResponse>, Status> {
        let req = request.into_inner();

        let ir: Value = serde_json::from_str(&req.ir_json)
            .map_err(|e| Status::invalid_argument(format!("Invalid IR JSON: {}", e)))?;

        // Look up previous version
        let prev_version: Option<(String,)> = sqlx::query_as(
            "SELECT ir_json FROM workflow_versions WHERE workflow_id = ? ORDER BY registered_at DESC LIMIT 1"
        )
        .bind(&req.workflow_id)
        .fetch_optional(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        let compatibility = match prev_version {
            None => "NEW",
            Some((prev_ir_json,)) => {
                if prev_ir_json == req.ir_json {
                    "IDENTICAL"
                } else if let Ok(prev_ir) = serde_json::from_str::<Value>(&prev_ir_json) {
                    analyze_compatibility(&prev_ir, &ir)
                } else {
                    "BREAKING"
                }
            }
        };

        // Store in versions table (INSERT OR IGNORE for SQLite, ON CONFLICT DO NOTHING for PG)
        let sql = if self.is_postgres {
            "INSERT INTO workflow_versions (workflow_id, version_hash, ir_json, compatibility)
             VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING"
        } else {
            "INSERT OR IGNORE INTO workflow_versions (workflow_id, version_hash, ir_json, compatibility)
             VALUES (?, ?, ?, ?)"
        };
        sqlx::query(sql)
        .bind(&req.workflow_id)
        .bind(&req.version_hash)
        .bind(&req.ir_json)
        .bind(compatibility)
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        tracing::info!(
            workflow_id = req.workflow_id,
            version_hash = req.version_hash,
            compatibility = compatibility,
            "Registering workflow"
        );

        let key = format!("{}:{}", req.workflow_id, req.version_hash);
        self.registry.write().await.insert(key, ir);

        let message = match compatibility {
            "SAFE" => "New nodes added. Old executions continue on previous version.".to_string(),
            "BREAKING" => "Breaking change detected. Run parallel workers for in-flight executions.".to_string(),
            "IDENTICAL" => "No changes detected.".to_string(),
            _ => "New workflow registered.".to_string(),
        };

        Ok(Response::new(AckResponse {
            ok: true,
            compatibility: compatibility.to_string(),
            message,
        }))
    }

    async fn start_execution(
        &self,
        request: Request<StartRequest>,
    ) -> Result<Response<StartResponse>, Status> {
        let req = request.into_inner();
        let execution_id = format!("exec-{}", Uuid::new_v4());

        self.metrics.executions_started.fetch_add(1, Ordering::Relaxed);
        tracing::info!(
            execution_id = %execution_id,
            workflow_id = %req.workflow_id,
            version_hash = %req.version_hash.chars().take(12).collect::<String>(),
            "Execution started"
        );

        sqlx::query(
            "INSERT INTO workflow_executions (execution_id, workflow_id, version_hash, status, input_json)
             VALUES (?, ?, ?, 'RUNNING', ?)"
        )
        .bind(&execution_id)
        .bind(&req.workflow_id)
        .bind(&req.version_hash)
        .bind(&req.input_json)
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        self.schedule_ready_nodes(&execution_id, &req.workflow_id, &req.version_hash)
            .await?;

        Ok(Response::new(StartResponse { execution_id }))
    }

    async fn poll_task(
        &self,
        request: Request<PollRequest>,
    ) -> Result<Response<PollResponse>, Status> {
        let req = request.into_inner();

        let now = self.now_sql();
        let poll_sql = format!(
            "SELECT task_id, execution_id, node_id, version_hash, input_json, idempotency_key, node_type, map_item_json, map_index, map_total, map_parent_node_id, sub_execution_id, sub_workflow_id, sub_input_json
             FROM task_queue
             WHERE version_hash = ? AND status = 'READY' AND scheduled_at <= {}
             ORDER BY scheduled_at ASC
             LIMIT 1", now
        );

        let task: Option<(String, String, String, String, Option<String>, Option<String>, Option<String>, Option<String>, Option<i32>, Option<i32>, Option<String>, Option<String>, Option<String>, Option<String>)> = sqlx::query_as(&poll_sql)
        .bind(&req.version_hash)
        .fetch_optional(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        match task {
            Some((task_id, execution_id, node_id, version_hash, _input_json, idempotency_key, db_node_type, map_item_json, map_index, map_total, map_parent_node_id, sub_execution_id, sub_workflow_id, sub_input_json)) => {
                // Lock the task
                let lock_sql = format!("UPDATE task_queue SET status = 'RUNNING', locked_by = ?, locked_at = {} WHERE task_id = ?", now);
                sqlx::query(&lock_sql)
                    .bind(&req.worker_id)
                    .bind(&task_id)
                    .execute(&self.db)
                    .await
                    .map_err(|e| Status::internal(e.to_string()))?;

                // Build input from execution input + dependency outputs
                let exec_row: Option<(Option<String>, String)> = sqlx::query_as(
                    "SELECT input_json, workflow_id FROM workflow_executions WHERE execution_id = ?"
                )
                .bind(&execution_id)
                .fetch_optional(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;

                let (exec_input, workflow_id) = exec_row
                    .ok_or_else(|| Status::internal("Execution not found"))?;

                // Get dependency outputs from events
                let registry = self.registry.read().await;
                let key = format!("{}:{}", workflow_id, version_hash);
                let ir = registry.get(&key);

                let mut deps_output: HashMap<String, Value> = HashMap::new();

                // Resolve node type: prefer db_node_type (set for MAP_SUBTASK), then IR, then fallback
                let is_map_subtask = db_node_type.as_deref() == Some("MAP_SUBTASK");
                let response_node_id = if is_map_subtask {
                    map_parent_node_id.clone().unwrap_or_else(|| node_id.clone())
                } else {
                    node_id.clone()
                };
                let node_type = if let Some(ref dbt) = db_node_type {
                    if !dbt.is_empty() { dbt.clone() } else {
                        ir.and_then(|ir_val| ir_val.get("nodes"))
                            .and_then(|n| n.get(&node_id))
                            .and_then(|n| n.get("type"))
                            .and_then(|t| t.as_str())
                            .unwrap_or("EFFECT")
                            .to_string()
                    }
                } else {
                    ir.and_then(|ir_val| ir_val.get("nodes"))
                        .and_then(|n| n.get(&node_id))
                        .and_then(|n| n.get("type"))
                        .and_then(|t| t.as_str())
                        .unwrap_or("EFFECT")
                        .to_string()
                };
                let ir_lookup_node_id = if is_map_subtask {
                    response_node_id.clone()
                } else {
                    node_id.clone()
                };

                // TIMER nodes: auto-complete server-side, no worker needed
                if node_type == "TIMER" {
                    // Read delay_seconds from IR
                    let delay_secs = ir
                        .and_then(|ir_val| ir_val.get("nodes"))
                        .and_then(|n| n.get(&node_id))
                        .and_then(|n| n.get("delay_seconds"))
                        .and_then(|d| d.as_i64())
                        .unwrap_or(0);

                    let output = serde_json::json!({
                        "waited_until": Utc::now().to_rfc3339(),
                        "delay_seconds": delay_secs,
                    });

                    // Mark task DONE
                    sqlx::query("UPDATE task_queue SET status = 'DONE' WHERE task_id = ?")
                        .bind(&task_id)
                        .execute(&self.db)
                        .await
                        .map_err(|e| Status::internal(e.to_string()))?;

                    self.metrics.tasks_completed.fetch_add(1, Ordering::Relaxed);

                    // Insert NodeCompleted event
                    let event_id = format!("evt-{}", Uuid::new_v4());
                    let seq_id = self.get_next_sequence_id(&execution_id).await?;
                    let payload = serde_json::json!({
                        "node_id": node_id,
                        "output": output,
                    });
                    sqlx::query(
                        "INSERT INTO events (event_id, execution_id, sequence_id, event_type, payload)
                         VALUES (?, ?, ?, 'NodeCompleted', ?)"
                    )
                    .bind(&event_id)
                    .bind(&execution_id)
                    .bind(seq_id)
                    .bind(serde_json::to_string(&payload).unwrap_or_default())
                    .execute(&self.db)
                    .await
                    .map_err(|e| Status::internal(e.to_string()))?;

                    tracing::info!(
                        execution_id = %execution_id,
                        node_id = %node_id,
                        delay_seconds = delay_secs,
                        "TIMER auto-completed"
                    );

                    // Schedule downstream nodes
                    self.schedule_ready_nodes(&execution_id, &workflow_id, &version_hash).await?;
                    self.check_execution_complete(&execution_id, &workflow_id, &version_hash).await?;

                    // Return empty response — no task for worker to process
                    return Ok(Response::new(PollResponse {
                        has_task: false,
                        task_id: String::new(),
                        execution_id: String::new(),
                        node_id: String::new(),
                        input_json: String::new(),
                        idempotency_key: String::new(),
                        node_type: String::new(),
                        map_item_json: String::new(),
                        is_map_subtask: false,
                        map_index: 0,
                        map_total: 0,
                        sub_execution_id: String::new(),
                        sub_workflow_id: String::new(),
                        sub_input_json: String::new(),
                    }));
                }

                // For HUMAN_APPROVAL nodes, set approval_status to PENDING
                if node_type == "HUMAN_APPROVAL" {
                    sqlx::query("UPDATE task_queue SET approval_status = 'PENDING' WHERE task_id = ?")
                        .bind(&task_id)
                        .execute(&self.db)
                        .await
                        .map_err(|e| Status::internal(e.to_string()))?;
                }

                if let Some(ir) = ir {
                    if let Some(deps) = ir
                        .get("nodes")
                        .and_then(|n| n.get(&ir_lookup_node_id))
                        .and_then(|n| n.get("dependencies"))
                        .and_then(|d| d.as_array())
                    {
                        for dep in deps {
                            if let Some(dep_id) = dep.as_str() {
                                if let Some(payload) = self.find_node_completed_event(&execution_id, dep_id).await? {
                                    if let Ok(payload_val) = serde_json::from_str::<Value>(&payload) {
                                        if let Some(output) = payload_val.get("output") {
                                            // Resolve claim check if needed
                                            let resolved = if let Some(output_str) = output.as_str() {
                                                if let Ok(resolved_str) = self.resolve_payload(output_str).await {
                                                    serde_json::from_str::<Value>(&resolved_str).unwrap_or(output.clone())
                                                } else {
                                                    output.clone()
                                                }
                                            } else if output.get("__nexum_claim_check__").and_then(|v| v.as_bool()).unwrap_or(false) {
                                                let output_str = serde_json::to_string(output).unwrap_or_default();
                                                if let Ok(resolved_str) = self.resolve_payload(&output_str).await {
                                                    serde_json::from_str::<Value>(&resolved_str).unwrap_or(output.clone())
                                                } else {
                                                    output.clone()
                                                }
                                            } else {
                                                output.clone()
                                            };
                                            deps_output.insert(dep_id.to_string(), resolved);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                let input_val = serde_json::json!({
                    "input": exec_input.and_then(|s| serde_json::from_str::<Value>(&s).ok()).unwrap_or(Value::Null),
                    "deps": deps_output,
                });

                tracing::info!(
                    task_id = task_id,
                    node_id = node_id,
                    worker = req.worker_id,
                    "Task polled"
                );

                Ok(Response::new(PollResponse {
                    has_task: true,
                    task_id,
                    execution_id,
                    node_id: response_node_id,
                    input_json: serde_json::to_string(&input_val).unwrap_or_default(),
                    idempotency_key: idempotency_key.unwrap_or_default(),
                    node_type,
                    map_item_json: map_item_json.unwrap_or_default(),
                    is_map_subtask,
                    map_index: map_index.unwrap_or(0),
                    map_total: map_total.unwrap_or(0),
                    sub_execution_id: sub_execution_id.unwrap_or_default(),
                    sub_workflow_id: sub_workflow_id.unwrap_or_default(),
                    sub_input_json: sub_input_json.unwrap_or_default(),
                }))
            }
            None => Ok(Response::new(PollResponse {
                has_task: false,
                task_id: String::new(),
                execution_id: String::new(),
                node_id: String::new(),
                input_json: String::new(),
                idempotency_key: String::new(),
                node_type: String::new(),
                map_item_json: String::new(),
                is_map_subtask: false,
                map_index: 0,
                map_total: 0,
                sub_execution_id: String::new(),
                sub_workflow_id: String::new(),
                sub_input_json: String::new(),
            })),
        }
    }

    async fn complete_task(
        &self,
        request: Request<CompleteRequest>,
    ) -> Result<Response<AckResponse>, Status> {
        let req = request.into_inner();

        // Get task info
        let task: (String, String, String, Option<String>, Option<i32>, Option<i32>, Option<String>, Option<String>) = sqlx::query_as(
            "SELECT execution_id, node_id, version_hash, node_type, map_index, map_total, map_parent_node_id, sub_execution_id FROM task_queue WHERE task_id = ?"
        )
        .bind(&req.task_id)
        .fetch_one(&self.db)
        .await
        .map_err(|e| Status::not_found(format!("Task not found: {}", e)))?;

        let (execution_id, node_id, version_hash, db_node_type, map_index, map_total, map_parent_node_id, sub_execution_id) = task;
        let db_node_type_str = db_node_type.unwrap_or_default();

        tracing::info!(
            execution_id = %execution_id,
            node_id = %node_id,
            "nexum.task.complete.start"
        );

        // --- SUBWORKFLOW coordinator (phase 1): start child execution ---
        if db_node_type_str == "SUBWORKFLOW" && sub_execution_id.is_none() {
            let payload: serde_json::Value = serde_json::from_str(&req.output_json)
                .map_err(|e| Status::internal(format!("Invalid SUBWORKFLOW output: {}", e)))?;
            let sub_wf_id = payload["subWorkflowId"].as_str().unwrap_or_default().to_string();
            let child_input = payload["childInput"].clone();

            // Look up the latest version_hash for the child workflow
            let child_version: Option<(String,)> = sqlx::query_as(
                "SELECT version_hash FROM workflow_versions WHERE workflow_id = ? ORDER BY registered_at DESC LIMIT 1"
            )
            .bind(&sub_wf_id)
            .fetch_optional(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

            let child_version_hash = child_version
                .ok_or_else(|| Status::not_found(format!("Child workflow not registered: {}", sub_wf_id)))?
                .0;

            // Start child execution with parent reference
            let child_exec_id = format!("exec-{}", Uuid::new_v4());
            sqlx::query(
                "INSERT INTO workflow_executions (execution_id, workflow_id, version_hash, status, input_json, parent_execution_id, parent_node_id)
                 VALUES (?, ?, ?, 'RUNNING', ?, ?, ?)"
            )
            .bind(&child_exec_id)
            .bind(&sub_wf_id)
            .bind(&child_version_hash)
            .bind(serde_json::to_string(&child_input).unwrap_or_default())
            .bind(&execution_id)
            .bind(&node_id)
            .execute(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

            self.metrics.executions_started.fetch_add(1, Ordering::Relaxed);

            // Update parent SUBWORKFLOW task with child exec id — keep status RUNNING
            sqlx::query("UPDATE task_queue SET sub_execution_id = ?, status = 'RUNNING' WHERE task_id = ?")
                .bind(&child_exec_id)
                .bind(&req.task_id)
                .execute(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;

            tracing::info!(
                execution_id = %execution_id,
                node_id = %node_id,
                child_execution_id = %child_exec_id,
                child_workflow = %sub_wf_id,
                "SUBWORKFLOW phase 2: child execution started"
            );

            // Schedule child's ready nodes
            self.schedule_ready_nodes(&child_exec_id, &sub_wf_id, &child_version_hash).await?;

            // DO NOT schedule parent's next nodes — wait for child to complete
            return Ok(Response::new(AckResponse { ok: true, compatibility: String::new(), message: String::new() }));
        }

        // Mark task as DONE
        sqlx::query("UPDATE task_queue SET status = 'DONE' WHERE task_id = ?")
            .bind(&req.task_id)
            .execute(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

        self.metrics.tasks_completed.fetch_add(1, Ordering::Relaxed);

        // Get workflow_id for this execution
        let exec_row: (String,) = sqlx::query_as(
            "SELECT workflow_id FROM workflow_executions WHERE execution_id = ?"
        )
        .bind(&execution_id)
        .fetch_one(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;
        let workflow_id = exec_row.0;

        // --- MAP coordinator (phase 1): fan-out sub-tasks ---
        if db_node_type_str == "MAP" {
            let items: Vec<serde_json::Value> = serde_json::from_str(&req.output_json)
                .map_err(|e| Status::internal(format!("MAP items not a JSON array: {}", e)))?;
            let total = items.len() as i32;

            tracing::info!(
                execution_id = %execution_id,
                node_id = %node_id,
                total = total,
                "MAP coordinator complete, fanning out sub-tasks"
            );

            let now = self.now_sql();
            let map_insert_sql = format!(
                "INSERT INTO task_queue (task_id, execution_id, node_id, version_hash, idempotency_key, status, node_type, map_item_json, map_index, map_total, map_parent_node_id, scheduled_at)
                 VALUES (?, ?, ?, ?, ?, 'READY', 'MAP_SUBTASK', ?, ?, ?, ?, {})", now
            );

            for (index, item) in items.iter().enumerate() {
                let sub_task_id = format!("task-{}", Uuid::new_v4());
                let sub_node_id = format!("{}__{}", node_id, index);
                let idempotency_key = format!("{}:{}:{}", execution_id, sub_node_id, version_hash);

                sqlx::query(&map_insert_sql)
                .bind(&sub_task_id)
                .bind(&execution_id)
                .bind(&sub_node_id)
                .bind(&version_hash)
                .bind(&idempotency_key)
                .bind(item.to_string())
                .bind(index as i32)
                .bind(total)
                .bind(&node_id)
                .execute(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;
            }

            // Don't insert NodeCompleted yet — wait for all sub-tasks
            return Ok(Response::new(AckResponse { ok: true, compatibility: String::new(), message: String::new() }));
        }

        // --- MAP_SUBTASK (phase 2): fan-in ---
        if db_node_type_str == "MAP_SUBTASK" {
            let parent_node_id = map_parent_node_id.unwrap_or_default();
            let idx = map_index.unwrap_or(0);
            let total = map_total.unwrap_or(0);

            // Store individual result (upsert)
            let upsert_sql = if self.is_postgres {
                "INSERT INTO map_results (execution_id, map_node_id, item_index, result_json)
                 VALUES (?, ?, ?, ?)
                 ON CONFLICT (execution_id, map_node_id, item_index) DO UPDATE SET result_json = EXCLUDED.result_json"
            } else {
                "INSERT OR REPLACE INTO map_results (execution_id, map_node_id, item_index, result_json)
                 VALUES (?, ?, ?, ?)"
            };
            sqlx::query(upsert_sql)
            .bind(&execution_id)
            .bind(&parent_node_id)
            .bind(idx)
            .bind(&req.output_json)
            .execute(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

            // Check if all sub-tasks done
            let completed_count: (i64,) = sqlx::query_as(
                "SELECT COUNT(*) FROM map_results WHERE execution_id = ? AND map_node_id = ?"
            )
            .bind(&execution_id)
            .bind(&parent_node_id)
            .fetch_one(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

            tracing::info!(
                execution_id = %execution_id,
                map_node_id = %parent_node_id,
                completed = completed_count.0,
                total = total,
                "MAP sub-task completed"
            );

            if completed_count.0 == total as i64 {
                // All sub-tasks done! Gather results and emit NodeCompleted for the MAP node
                let result_rows: Vec<(String,)> = sqlx::query_as(
                    "SELECT result_json FROM map_results WHERE execution_id = ? AND map_node_id = ? ORDER BY item_index"
                )
                .bind(&execution_id)
                .bind(&parent_node_id)
                .fetch_all(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;

                let results_array: Vec<serde_json::Value> = result_rows
                    .iter()
                    .map(|(rj,)| serde_json::from_str(rj).unwrap_or(Value::Null))
                    .collect();

                let output_json = serde_json::to_string(&results_array).unwrap_or_default();
                let stored_output = self.store_payload(&execution_id, &parent_node_id, &output_json).await?;
                let output: Value = serde_json::from_str(&stored_output).unwrap_or(Value::Null);

                let event_id = format!("evt-{}", Uuid::new_v4());
                let seq_id = self.get_next_sequence_id(&execution_id).await?;
                let payload = serde_json::json!({
                    "node_id": parent_node_id,
                    "output": output,
                });

                sqlx::query(
                    "INSERT INTO events (event_id, execution_id, sequence_id, event_type, payload)
                     VALUES (?, ?, ?, 'NodeCompleted', ?)"
                )
                .bind(&event_id)
                .bind(&execution_id)
                .bind(seq_id)
                .bind(serde_json::to_string(&payload).unwrap_or_default())
                .execute(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;

                tracing::info!(
                    execution_id = %execution_id,
                    node_id = %parent_node_id,
                    total = total,
                    "All MAP sub-tasks complete, scheduling downstream"
                );

                self.schedule_ready_nodes(&execution_id, &workflow_id, &version_hash).await?;
                self.check_execution_complete(&execution_id, &workflow_id, &version_hash).await?;
            }

            return Ok(Response::new(AckResponse { ok: true, compatibility: String::new(), message: String::new() }));
        }

        // --- Normal task completion (COMPUTE/EFFECT/REDUCE/ROUTER) ---

        // Store payload with claim check for large outputs
        let stored_output = self.store_payload(&execution_id, &node_id, &req.output_json).await?;
        let output: Value = serde_json::from_str(&stored_output).unwrap_or(Value::Null);

        // Insert NodeCompleted event
        let event_id = format!("evt-{}", Uuid::new_v4());
        let seq_id = self.get_next_sequence_id(&execution_id).await?;
        let payload = serde_json::json!({
            "node_id": node_id,
            "output": output,
        });

        sqlx::query(
            "INSERT INTO events (event_id, execution_id, sequence_id, event_type, payload)
             VALUES (?, ?, ?, 'NodeCompleted', ?)"
        )
        .bind(&event_id)
        .bind(&execution_id)
        .bind(seq_id)
        .bind(serde_json::to_string(&payload).unwrap_or_default())
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        tracing::info!(
            task_id = %req.task_id,
            node_id = %node_id,
            execution_id = %execution_id,
            "Task completed"
        );

        // Check if this is a ROUTER node
        let node_type = {
            let registry = self.registry.read().await;
            let reg_key = format!("{}:{}", workflow_id, version_hash);
            registry.get(&reg_key)
                .and_then(|ir| ir.get("nodes"))
                .and_then(|n| n.get(&node_id))
                .and_then(|n| n.get("type"))
                .and_then(|t| t.as_str())
                .unwrap_or("COMPUTE")
                .to_string()
        };

        if node_type == "ROUTER" {
            // Only schedule the node named in output.routed_to
            let output: Value = serde_json::from_str(&req.output_json).unwrap_or(Value::Null);
            let routed_to = output.get("routed_to").and_then(|r| r.as_str()).unwrap_or("");
            if !routed_to.is_empty() {
                let route_task_id = format!("task-{}", Uuid::new_v4());
                let idempotency_key = format!("{}:{}:{}", execution_id, routed_to, version_hash);
                let sql = if self.is_postgres {
                    "INSERT INTO task_queue (task_id, execution_id, node_id, version_hash, idempotency_key, status)
                     VALUES (?, ?, ?, ?, ?, 'READY') ON CONFLICT DO NOTHING"
                } else {
                    "INSERT OR IGNORE INTO task_queue (task_id, execution_id, node_id, version_hash, idempotency_key, status)
                     VALUES (?, ?, ?, ?, ?, 'READY')"
                };
                sqlx::query(sql)
                .bind(&route_task_id)
                .bind(&execution_id)
                .bind(routed_to)
                .bind(&version_hash)
                .bind(&idempotency_key)
                .execute(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;

                tracing::info!(router = %node_id, routed_to = routed_to, "Router decision");
            }
        } else {
            // Normal: schedule all newly unblocked nodes
            self.schedule_ready_nodes(&execution_id, &workflow_id, &version_hash)
                .await?;
        }

        // Check if execution is complete
        self.check_execution_complete(&execution_id, &workflow_id, &version_hash)
            .await?;

        Ok(Response::new(AckResponse { ok: true, compatibility: String::new(), message: String::new() }))
    }

    async fn fail_task(
        &self,
        request: Request<FailRequest>,
    ) -> Result<Response<AckResponse>, Status> {
        let req = request.into_inner();

        let task: (String, String, i64, String) = sqlx::query_as(
            "SELECT execution_id, node_id, retry_count, version_hash FROM task_queue WHERE task_id = ?"
        )
        .bind(&req.task_id)
        .fetch_one(&self.db)
        .await
        .map_err(|e| Status::not_found(format!("Task not found: {}", e)))?;

        let (execution_id, node_id, retry_count, _version_hash) = task;
        let max_retries: i64 = 3;

        tracing::info!(
            execution_id = %execution_id,
            node_id = %node_id,
            retry_count = retry_count,
            will_retry = retry_count < max_retries,
            "nexum.task.fail"
        );

        if retry_count < max_retries {
            // Retry: reset to READY with exponential backoff
            let backoff_secs = (2_i64.pow(retry_count as u32)).min(30);
            let retry_sql = if self.is_postgres {
                format!(
                    "UPDATE task_queue SET status = 'READY', locked_by = NULL, locked_at = NULL,
                     retry_count = retry_count + 1,
                     scheduled_at = NOW() + INTERVAL '{} seconds'
                     WHERE task_id = ?", backoff_secs
                )
            } else {
                "UPDATE task_queue SET status = 'READY', locked_by = NULL, locked_at = NULL,
                 retry_count = retry_count + 1,
                 scheduled_at = datetime('now', ? || ' seconds')
                 WHERE task_id = ?".to_string()
            };

            if self.is_postgres {
                sqlx::query(&retry_sql)
                    .bind(&req.task_id)
                    .execute(&self.db)
                    .await
                    .map_err(|e| Status::internal(e.to_string()))?;
            } else {
                sqlx::query(&retry_sql)
                    .bind(format!("+{}", backoff_secs))
                    .bind(&req.task_id)
                    .execute(&self.db)
                    .await
                    .map_err(|e| Status::internal(e.to_string()))?;
            }

            self.metrics.tasks_retried.fetch_add(1, Ordering::Relaxed);
            tracing::warn!(
                task_id = %req.task_id,
                node_id = %node_id,
                retry = retry_count + 1,
                max = max_retries,
                "Task failed, scheduling retry"
            );
        } else {
            // Exhausted retries: mark FAILED
            sqlx::query("UPDATE task_queue SET status = 'FAILED' WHERE task_id = ?")
                .bind(&req.task_id)
                .execute(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;

            let event_id = format!("evt-{}", Uuid::new_v4());
            let seq_id = self.get_next_sequence_id(&execution_id).await?;
            let payload = serde_json::json!({
                "node_id": node_id,
                "error": req.error_message,
                "final_retry": retry_count,
            });

            sqlx::query(
                "INSERT INTO events (event_id, execution_id, sequence_id, event_type, payload)
                 VALUES (?, ?, ?, 'NodeFailed', ?)"
            )
            .bind(&event_id)
            .bind(&execution_id)
            .bind(seq_id)
            .bind(serde_json::to_string(&payload).unwrap_or_default())
            .execute(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

            sqlx::query("UPDATE workflow_executions SET status = 'FAILED' WHERE execution_id = ?")
                .bind(&execution_id)
                .execute(&self.db)
                .await
                .map_err(|e| Status::internal(e.to_string()))?;

            self.metrics.tasks_failed.fetch_add(1, Ordering::Relaxed);
            self.metrics.executions_failed.fetch_add(1, Ordering::Relaxed);
            tracing::error!(
                task_id = %req.task_id,
                node_id = %node_id,
                execution_id = %execution_id,
                "Task failed after max retries"
            );
        }

        Ok(Response::new(AckResponse { ok: true, compatibility: String::new(), message: String::new() }))
    }

    async fn get_status(
        &self,
        request: Request<StatusRequest>,
    ) -> Result<Response<StatusResponse>, Status> {
        let req = request.into_inner();

        let exec: (String,) = sqlx::query_as(
            "SELECT status FROM workflow_executions WHERE execution_id = ?"
        )
        .bind(&req.execution_id)
        .fetch_one(&self.db)
        .await
        .map_err(|e| Status::not_found(format!("Execution not found: {}", e)))?;

        let events: Vec<(String,)> = sqlx::query_as(
            "SELECT payload FROM events WHERE execution_id = ? AND event_type = 'NodeCompleted' ORDER BY sequence_id"
        )
        .bind(&req.execution_id)
        .fetch_all(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        let mut completed_nodes: HashMap<String, Value> = HashMap::new();
        for (payload_str,) in events {
            if let Ok(payload) = serde_json::from_str::<Value>(&payload_str) {
                if let (Some(node_id), Some(output)) =
                    (payload.get("node_id").and_then(|n| n.as_str()), payload.get("output"))
                {
                    completed_nodes.insert(node_id.to_string(), output.clone());
                }
            }
        }

        Ok(Response::new(StatusResponse {
            status: exec.0,
            completed_nodes_json: serde_json::to_string(&completed_nodes).unwrap_or_default(),
        }))
    }

    async fn list_executions(
        &self,
        request: Request<ListRequest>,
    ) -> Result<Response<ListResponse>, Status> {
        let req = request.into_inner();
        let limit = if req.limit > 0 { req.limit } else { 20 };

        let executions: Vec<(String, String, String, String, String)> = if !req.workflow_id.is_empty() && !req.status.is_empty() {
            sqlx::query_as(
                "SELECT execution_id, workflow_id, version_hash, status, created_at
                 FROM workflow_executions WHERE workflow_id = ? AND status = ?
                 ORDER BY created_at DESC LIMIT ?"
            ).bind(&req.workflow_id).bind(&req.status).bind(limit)
            .fetch_all(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?
        } else if !req.workflow_id.is_empty() {
            sqlx::query_as(
                "SELECT execution_id, workflow_id, version_hash, status, created_at
                 FROM workflow_executions WHERE workflow_id = ?
                 ORDER BY created_at DESC LIMIT ?"
            ).bind(&req.workflow_id).bind(limit)
            .fetch_all(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?
        } else if !req.status.is_empty() {
            sqlx::query_as(
                "SELECT execution_id, workflow_id, version_hash, status, created_at
                 FROM workflow_executions WHERE status = ?
                 ORDER BY created_at DESC LIMIT ?"
            ).bind(&req.status).bind(limit)
            .fetch_all(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?
        } else {
            sqlx::query_as(
                "SELECT execution_id, workflow_id, version_hash, status, created_at
                 FROM workflow_executions ORDER BY created_at DESC LIMIT ?"
            ).bind(limit)
            .fetch_all(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?
        };

        Ok(Response::new(ListResponse {
            executions: executions.into_iter().map(|(execution_id, workflow_id, version_hash, status, created_at)| {
                ExecutionSummary { execution_id, workflow_id, version_hash, status, created_at }
            }).collect(),
        }))
    }

    async fn cancel_execution(
        &self,
        request: Request<CancelRequest>,
    ) -> Result<Response<AckResponse>, Status> {
        let req = request.into_inner();

        // Cancel all READY and RUNNING tasks
        sqlx::query(
            "UPDATE task_queue SET status = 'CANCELLED'
             WHERE execution_id = ? AND status IN ('READY', 'RUNNING')"
        )
        .bind(&req.execution_id)
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        // Mark execution as CANCELLED
        sqlx::query(
            "UPDATE workflow_executions SET status = 'CANCELLED' WHERE execution_id = ?"
        )
        .bind(&req.execution_id)
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        // Insert cancellation event
        let event_id = format!("evt-{}", Uuid::new_v4());
        let seq_id = self.get_next_sequence_id(&req.execution_id).await?;
        sqlx::query(
            "INSERT INTO events (event_id, execution_id, sequence_id, event_type, payload)
             VALUES (?, ?, ?, 'ExecutionCancelled', '{}')"
        )
        .bind(&event_id)
        .bind(&req.execution_id)
        .bind(seq_id)
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        tracing::info!(execution_id = req.execution_id, "Execution cancelled");

        Ok(Response::new(AckResponse { ok: true, compatibility: String::new(), message: "Execution cancelled".to_string() }))
    }

    async fn list_workflow_versions(
        &self,
        request: Request<ListVersionsRequest>,
    ) -> Result<Response<ListVersionsResponse>, Status> {
        let req = request.into_inner();

        let rows: Vec<(String, String, String, String)> = sqlx::query_as(
            "SELECT wv.workflow_id, wv.version_hash, wv.compatibility, wv.registered_at
             FROM workflow_versions wv
             WHERE wv.workflow_id = ?
             ORDER BY wv.registered_at DESC"
        )
        .bind(&req.workflow_id)
        .fetch_all(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        let mut versions = Vec::new();
        for (workflow_id, version_hash, compatibility, registered_at) in rows {
            let active_count: (i64,) = sqlx::query_as(
                "SELECT COUNT(*) FROM workflow_executions
                 WHERE version_hash = ? AND status = 'RUNNING'"
            )
            .bind(&version_hash)
            .fetch_one(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

            versions.push(VersionInfo {
                workflow_id,
                version_hash,
                compatibility,
                registered_at,
                active_executions: active_count.0 as i32,
            });
        }

        Ok(Response::new(ListVersionsResponse { versions }))
    }

    async fn approve_task(
        &self,
        request: Request<ApproveRequest>,
    ) -> Result<Response<AckResponse>, Status> {
        let req = request.into_inner();

        let task: Option<(String, String)> = sqlx::query_as(
            "SELECT task_id, status FROM task_queue
             WHERE execution_id = ? AND node_id = ? AND status = 'RUNNING'"
        )
        .bind(&req.execution_id)
        .bind(&req.node_id)
        .fetch_optional(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        let (task_id, _) = task.ok_or_else(|| Status::not_found("No pending approval task found"))?;

        // Mark as approved
        sqlx::query(
            "UPDATE task_queue SET approval_status = 'APPROVED', approver = ?, approval_comment = ?
             WHERE task_id = ?"
        )
        .bind(&req.approver)
        .bind(&req.comment)
        .bind(&task_id)
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        // Synthesize output: complete the HUMAN_APPROVAL task
        let output = serde_json::json!({
            "approved": true,
            "approver": req.approver,
            "comment": req.comment,
        });

        // Insert NodeCompleted event directly (no worker needed)
        let event_id = format!("evt-{}", Uuid::new_v4());
        let seq_id = self.get_next_sequence_id(&req.execution_id).await?;
        let payload = serde_json::json!({
            "node_id": req.node_id,
            "output": output,
        });
        sqlx::query(
            "INSERT INTO events (event_id, execution_id, sequence_id, event_type, payload)
             VALUES (?, ?, ?, 'NodeCompleted', ?)"
        )
        .bind(&event_id)
        .bind(&req.execution_id)
        .bind(seq_id)
        .bind(serde_json::to_string(&payload).unwrap_or_default())
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        // Mark task DONE
        sqlx::query("UPDATE task_queue SET status = 'DONE' WHERE task_id = ?")
            .bind(&task_id)
            .execute(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

        // Get workflow info to schedule next nodes
        let exec_row: (String, String) = sqlx::query_as(
            "SELECT workflow_id, version_hash FROM workflow_executions WHERE execution_id = ?"
        )
        .bind(&req.execution_id)
        .fetch_one(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        let (workflow_id, version_hash) = exec_row;
        self.schedule_ready_nodes(&req.execution_id, &workflow_id, &version_hash).await?;
        self.check_execution_complete(&req.execution_id, &workflow_id, &version_hash).await?;

        tracing::info!(
            execution_id = %req.execution_id,
            node_id = %req.node_id,
            approver = %req.approver,
            "Task approved"
        );

        Ok(Response::new(AckResponse { ok: true, compatibility: String::new(), message: "Approved".to_string() }))
    }

    async fn reject_task(
        &self,
        request: Request<RejectRequest>,
    ) -> Result<Response<AckResponse>, Status> {
        let req = request.into_inner();

        let task: Option<(String,)> = sqlx::query_as(
            "SELECT task_id FROM task_queue
             WHERE execution_id = ? AND node_id = ? AND status = 'RUNNING'"
        )
        .bind(&req.execution_id)
        .bind(&req.node_id)
        .fetch_optional(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        let (task_id,) = task.ok_or_else(|| Status::not_found("No pending approval task found"))?;

        // Mark task FAILED
        sqlx::query("UPDATE task_queue SET status = 'FAILED', approval_status = 'REJECTED', approver = ? WHERE task_id = ?")
            .bind(&req.approver)
            .bind(&task_id)
            .execute(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

        // Insert NodeFailed event
        let event_id = format!("evt-{}", Uuid::new_v4());
        let seq_id = self.get_next_sequence_id(&req.execution_id).await?;
        let payload = serde_json::json!({
            "node_id": req.node_id,
            "error": format!("Rejected by {}: {}", req.approver, req.reason),
        });
        sqlx::query(
            "INSERT INTO events (event_id, execution_id, sequence_id, event_type, payload)
             VALUES (?, ?, ?, 'NodeFailed', ?)"
        )
        .bind(&event_id)
        .bind(&req.execution_id)
        .bind(seq_id)
        .bind(serde_json::to_string(&payload).unwrap_or_default())
        .execute(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        sqlx::query("UPDATE workflow_executions SET status = 'FAILED' WHERE execution_id = ?")
            .bind(&req.execution_id)
            .execute(&self.db)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

        tracing::warn!(
            execution_id = %req.execution_id,
            node_id = %req.node_id,
            reason = %req.reason,
            "Task rejected"
        );

        Ok(Response::new(AckResponse { ok: true, compatibility: String::new(), message: "Rejected".to_string() }))
    }

    async fn get_pending_approvals(
        &self,
        _request: Request<EmptyRequest>,
    ) -> Result<Response<PendingApprovalsResponse>, Status> {
        let rows: Vec<(String, String, String, String)> = sqlx::query_as(
            "SELECT tq.execution_id, tq.node_id, we.workflow_id, tq.scheduled_at
             FROM task_queue tq JOIN workflow_executions we ON tq.execution_id = we.execution_id
             WHERE tq.status = 'RUNNING' AND tq.approval_status = 'PENDING'"
        )
        .fetch_all(&self.db)
        .await
        .map_err(|e| Status::internal(e.to_string()))?;

        let items = rows.into_iter().map(|(execution_id, node_id, workflow_id, started_at)| {
            PendingApprovalItem { execution_id, node_id, workflow_id, started_at }
        }).collect();

        Ok(Response::new(PendingApprovalsResponse { items }))
    }
}

fn init_tracer() -> Option<opentelemetry_sdk::trace::TracerProvider> {
    use opentelemetry_otlp::WithExportConfig;

    let endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
        .unwrap_or_else(|_| "http://localhost:4317".to_string());

    let exporter = opentelemetry_otlp::new_exporter()
        .tonic()
        .with_endpoint(endpoint);

    let result = opentelemetry_otlp::new_pipeline()
        .tracing()
        .with_exporter(exporter)
        .with_trace_config(
            opentelemetry_sdk::trace::Config::default()
                .with_resource(opentelemetry_sdk::Resource::new(vec![
                    opentelemetry::KeyValue::new("service.name", "nexum-server"),
                ]))
        )
        .install_batch(opentelemetry_sdk::runtime::Tokio);

    match result {
        Ok(provider) => {
            tracing::info!("OpenTelemetry tracing enabled");
            Some(provider)
        }
        Err(e) => {
            eprintln!("OpenTelemetry init failed (no collector?): {}. Continuing without tracing export.", e);
            None
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| "nexum_server=info".into());

    let provider = init_tracer();
    if let Some(ref provider) = provider {
        use tracing_subscriber::layer::SubscriberExt;
        let telemetry = tracing_opentelemetry::layer().with_tracer(provider.tracer("nexum"));
        tracing_subscriber::registry()
            .with(tracing_subscriber::fmt::layer())
            .with(telemetry)
            .with(filter)
            .init();
    } else {
        tracing_subscriber::fmt()
            .with_env_filter(filter)
            .init();
    }

    // Required for sqlx::AnyPool to work with multiple backends
    sqlx::any::install_default_drivers();

    let server = NexumServer::new().await?;
    let reclaim_db = server.db.clone();
    let reclaim_is_postgres = server.is_postgres;

    // Background task: reclaim stale RUNNING tasks
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(30)).await;
            let reclaim_sql = if reclaim_is_postgres {
                "UPDATE task_queue SET status = 'READY', locked_by = NULL, locked_at = NULL,
                 retry_count = retry_count + 1
                 WHERE status = 'RUNNING'
                 AND locked_at < NOW() - INTERVAL '60 seconds'
                 AND (approval_status IS NULL OR approval_status != 'PENDING')
                 AND (sub_execution_id IS NULL OR sub_execution_id = '')"
            } else {
                "UPDATE task_queue SET status = 'READY', locked_by = NULL, locked_at = NULL,
                 retry_count = retry_count + 1
                 WHERE status = 'RUNNING'
                 AND locked_at < datetime('now', '-60 seconds')
                 AND (approval_status IS NULL OR approval_status != 'PENDING')
                 AND (sub_execution_id IS NULL OR sub_execution_id = '')"
            };
            let result = sqlx::query(reclaim_sql)
                .execute(&reclaim_db)
                .await;

            match result {
                Ok(r) if r.rows_affected() > 0 => {
                    tracing::warn!(count = r.rows_affected(), "Reclaimed stale tasks");
                }
                _ => {}
            }
        }
    });

    // Metrics HTTP server on port 9090
    let metrics_arc = server.metrics.clone();
    tokio::spawn(async move {
        let app = axum::Router::new()
            .route("/metrics", axum::routing::get(move || {
                let m = metrics_arc.clone();
                async move { m.prometheus_text() }
            }))
            .route("/health", axum::routing::get(|| async { "ok" }));
        let listener = tokio::net::TcpListener::bind("0.0.0.0:9090").await.unwrap();
        tracing::info!("Metrics server on http://0.0.0.0:9090/metrics");
        axum::serve(listener, app).await.unwrap();
    });

    let addr = "[::1]:50051".parse()?;
    tracing::info!("Nexum server listening on {}", addr);

    Server::builder()
        .add_service(NexumServiceServer::new(server))
        .serve(addr)
        .await?;

    // Shutdown OpenTelemetry tracer on exit
    if provider.is_some() {
        opentelemetry::global::shutdown_tracer_provider();
    }

    Ok(())
}
