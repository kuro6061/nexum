"""
test_builder.py — Python SDK WorkflowBuilder のユニットテスト
"""

import hashlib
import json

import pytest
from pydantic import BaseModel

from nexum.builder import workflow


# ── サンプル出力スキーマ ─────────────────────────────────────────

class ValueOut(BaseModel):
    value: int

class TextOut(BaseModel):
    text: str


# ──────────────────────────────────────────────────────────────────
# 1. 基本チェーン: 依存関係が順番通りに設定される
# ──────────────────────────────────────────────────────────────────

def test_sequential_dependencies():
    """compute ノードが順番通りに依存関係を持つ"""
    wf = (
        workflow("test-chain")
        .compute("a", ValueOut, lambda ctx: ValueOut(value=1))
        .compute("b", ValueOut, lambda ctx: ValueOut(value=2))
        .compute("c", ValueOut, lambda ctx: ValueOut(value=3))
        .build()
    )
    ir = json.loads(wf.ir_json)["nodes"]
    assert ir["a"]["dependencies"] == []
    assert ir["b"]["dependencies"] == ["a"]
    assert ir["c"]["dependencies"] == ["a", "b"]


def test_effect_sequential_dependencies():
    """effect ノードが順番通りに依存関係を持つ"""
    async def fetch(ctx): return TextOut(text="ok")
    async def save(ctx): return ValueOut(value=1)

    wf = (
        workflow("test-effects")
        .effect("fetch", TextOut, fetch)
        .effect("save", ValueOut, save)
        .build()
    )
    ir = json.loads(wf.ir_json)["nodes"]
    assert ir["fetch"]["dependencies"] == []
    assert ir["save"]["dependencies"] == ["fetch"]


def test_node_types_in_ir():
    """type フィールドが正しく IR に反映される"""
    wf = (
        workflow("type-test")
        .compute("c", ValueOut, lambda ctx: ValueOut(value=0))
        .effect("e", ValueOut, lambda ctx: ValueOut(value=0))
        .build()
    )
    ir = json.loads(wf.ir_json)["nodes"]
    assert ir["c"]["type"] == "COMPUTE"
    assert ir["e"]["type"] == "EFFECT"


# ──────────────────────────────────────────────────────────────────
# 2. depends_on: 明示的な依存関係
# ──────────────────────────────────────────────────────────────────

def test_explicit_depends_on_fan_in():
    """depends_on でファンイン依存を指定できる"""
    wf = (
        workflow("fan-in")
        .effect("a", ValueOut, lambda ctx: ValueOut(value=1))
        .effect("b", ValueOut, lambda ctx: ValueOut(value=2))
        .effect("merge", ValueOut, lambda ctx: ValueOut(value=3), depends_on=["a", "b"])
        .build()
    )
    ir = json.loads(wf.ir_json)["nodes"]
    assert ir["a"]["dependencies"] == []
    assert ir["b"]["dependencies"] == ["a"]
    assert ir["merge"]["dependencies"] == ["a", "b"]


def test_depends_on_single_override():
    """depends_on=["x"] でシーケンシャルより少ない依存を持てる"""
    wf = (
        workflow("override")
        .compute("x", ValueOut, lambda ctx: ValueOut(value=1))
        .compute("y", ValueOut, lambda ctx: ValueOut(value=2))
        .compute("z", ValueOut, lambda ctx: ValueOut(value=3), depends_on=["x"])
        .build()
    )
    ir = json.loads(wf.ir_json)["nodes"]
    # z は y に依存しない
    assert ir["z"]["dependencies"] == ["x"]


# ──────────────────────────────────────────────────────────────────
# 3. TIMER ノード
# ──────────────────────────────────────────────────────────────────

def test_timer_node_type_and_delay():
    """timer ノードが TIMER type と delay_seconds を持つ"""
    wf = (
        workflow("timer-test")
        .effect("step1", ValueOut, lambda ctx: ValueOut(value=1))
        .timer("wait", delay_seconds=300)
        .build()
    )
    ir = json.loads(wf.ir_json)["nodes"]
    assert ir["wait"]["type"] == "TIMER"
    assert ir["wait"]["delay_seconds"] == 300
    assert ir["wait"]["dependencies"] == ["step1"]


# ──────────────────────────────────────────────────────────────────
# 4. build() 出力: WorkflowDef の各フィールド
# ──────────────────────────────────────────────────────────────────

def test_build_returns_correct_workflow_id():
    wf = workflow("my-wf").compute("a", ValueOut, lambda ctx: ValueOut(value=1)).build()
    assert wf.workflow_id == "my-wf"


def test_build_version_hash_is_sha256_prefixed():
    wf = workflow("hash-test").compute("a", ValueOut, lambda ctx: ValueOut(value=1)).build()
    assert wf.version_hash.startswith("sha256:")


def test_build_version_hash_is_deterministic():
    """同じワークフロー定義なら毎回同じ version_hash"""
    handler = lambda ctx: ValueOut(value=1)
    wf1 = workflow("det").compute("a", ValueOut, handler).build()
    wf2 = workflow("det").compute("a", ValueOut, handler).build()
    assert wf1.version_hash == wf2.version_hash


def test_build_different_nodes_give_different_hash():
    wf1 = workflow("diff").compute("a", ValueOut, lambda ctx: ValueOut(value=1)).build()
    wf2 = workflow("diff").compute("b", ValueOut, lambda ctx: ValueOut(value=1)).build()
    assert wf1.version_hash != wf2.version_hash


def test_build_ir_json_is_valid():
    wf = workflow("json-test").compute("a", ValueOut, lambda ctx: ValueOut(value=1)).build()
    parsed = json.loads(wf.ir_json)
    assert "nodes" in parsed
    assert "a" in parsed["nodes"]


def test_get_node_returns_node_def():
    handler = lambda ctx: ValueOut(value=99)
    wf = workflow("node-lookup").compute("mynode", ValueOut, handler).build()
    node = wf.get_node("mynode")
    assert node is not None
    assert node.id == "mynode"
    assert node.type == "COMPUTE"
    assert node.handler is handler


def test_get_node_returns_none_for_missing():
    wf = workflow("missing").compute("a", ValueOut, lambda ctx: ValueOut(value=1)).build()
    assert wf.get_node("nonexistent") is None


def test_nodes_list_length():
    wf = (
        workflow("multi")
        .compute("a", ValueOut, lambda ctx: ValueOut(value=1))
        .compute("b", ValueOut, lambda ctx: ValueOut(value=2))
        .effect("c", ValueOut, lambda ctx: ValueOut(value=3))
        .build()
    )
    assert len(wf.nodes) == 3


# ──────────────────────────────────────────────────────────────────
# 5. IR JSON の構造検証
# ──────────────────────────────────────────────────────────────────

def test_ir_version_hash_matches_ir_json():
    """version_hash は ir_json の sha256 と一致する"""
    wf = workflow("verify").compute("a", ValueOut, lambda ctx: ValueOut(value=1)).build()
    expected = "sha256:" + hashlib.sha256(wf.ir_json.encode()).hexdigest()
    assert wf.version_hash == expected
