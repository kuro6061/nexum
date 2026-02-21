import { spawn } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { existsSync } from 'fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
// Look for server binary relative to CLI package
const serverBin = join(__dirname, '../../../../target/debug/nexum-server.exe');

if (!existsSync(serverBin)) {
  console.error(`[nexum dev] Server binary not found at: ${serverBin}`);
  console.error('Run "cargo build" first to build the nexum-server binary.');
  process.exit(1);
}

const dbUrl = process.env.DATABASE_URL || 'sqlite://.nexum/local.db';
const dbType = dbUrl.startsWith('postgres') ? 'PostgreSQL' : 'SQLite';
console.log(`[nexum dev] Database: ${dbType} (${dbUrl})`);
console.log('[nexum dev] Starting Nexum server on localhost:50051');
const proc = spawn(serverBin, [], { stdio: 'inherit', env: { ...process.env } });
proc.on('exit', (code) => process.exit(code ?? 0));
process.on('SIGINT', () => proc.kill('SIGINT'));
