import json
from pathlib import Path

from multiverse_workflow.compiler.compiler import compile_package

ROOT = Path(__file__).parents[2]


def test_content_delivery_compiles_to_serializable_deterministic_plans() -> None:
    package_root = ROOT / "presets/content-delivery"
    binding = ROOT / "examples/bindings/content-local.yaml"

    first = compile_package(package_root, binding_path=binding)
    second = compile_package(package_root, binding_path=binding)

    assert first.ok
    assert list(first.plans) == ["delivery"]
    plan = first.plans["delivery"]
    assert plan.package_digest.startswith("sha256:")
    assert plan.binding_digest is not None
    assert plan.nodes["produce"]["defaults"]["retry"]["maxAttempts"] == 1
    assert any(edge["from"] == "produce" and edge["to"] == "verify" for edge in plan.edges)
    assert plan.compiled_plan_digest == second.plans["delivery"].compiled_plan_digest
    assert plan.as_dict()["defaults"] == {
        "runDeadlineSeconds": 604800,
        "callDeadlineSeconds": 3600,
        "maxAttempts": 1,
        "maxConcurrency": 4,
    }
    json.dumps(plan.as_dict(), sort_keys=True)


def test_compiler_reports_unresolved_binding_slot() -> None:
    package_root = ROOT / "presets/content-delivery"
    binding = ROOT / "examples/bindings/content-local.yaml"

    result = compile_package(package_root, binding_path=binding, omit_slots={"producer"})

    assert not result.ok
    assert result.diagnostics[0].code == "BINDING_UNRESOLVED"
    assert result.diagnostics[0].pointer == "/spec/slots/producer"
    assert result.diagnostics[0].file == str(binding.resolve())


def test_compiler_reports_an_unknown_executor_in_the_binding_file(tmp_path: Path) -> None:
    binding = tmp_path / "binding.yaml"
    binding.write_text(
        (ROOT / "examples/bindings/content-local.yaml")
        .read_text(encoding="utf-8")
        .replace("example.content-fixture.v1", "missing.executor.v1"),
        encoding="utf-8",
    )

    result = compile_package(ROOT / "presets/content-delivery", binding_path=binding)

    assert not result.ok
    assert result.diagnostics[0].code == "EXECUTOR_UNRESOLVED"
    assert result.diagnostics[0].file == str(binding.resolve())


def test_compiler_rejects_an_executor_adapter_mismatch(tmp_path: Path) -> None:
    binding = tmp_path / "binding.yaml"
    binding.write_text(
        (ROOT / "examples/bindings/content-local.yaml")
        .read_text(encoding="utf-8")
        .replace("adapter: builtin", "adapter: human", 1),
        encoding="utf-8",
    )

    result = compile_package(ROOT / "presets/content-delivery", binding_path=binding)

    assert not result.ok
    assert result.diagnostics[0].code == "EXECUTOR_ADAPTER_MISMATCH"


def test_compiler_inherits_workflow_retry_defaults_into_the_plan(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: work
  defaults:
    maxAttempts: 2
  nodes:
    work:
      type: call
      slot: worker
      inputSchema: schemas/value.json
      outputSchema: schemas/value.json
      input: {ref: input#}
      requires:
        capabilities: [data.process@1]
      effects:
        class: none
        actions: []
      next: complete
    complete:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
    )

    result = compile_package(package_root)

    assert result.ok
    assert result.plans["main"].nodes["work"]["defaults"]["retry"]["maxAttempts"] == 2


def test_compiler_allows_a_failed_call_to_feed_its_on_error_handler(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: work
  nodes:
    work:
      type: call
      slot: worker
      inputSchema: schemas/value.json
      outputSchema: schemas/value.json
      input: {ref: input#}
      requires:
        capabilities: [data.process@1]
      effects:
        class: none
        actions: []
      onError: handle-error
      next: complete
    handle-error:
      type: call
      slot: worker
      inputSchema: schemas/value.json
      outputSchema: schemas/value.json
      input: {ref: nodes.work.output#}
      requires:
        capabilities: [data.process@1]
      effects:
        class: none
        actions: []
      onError: failure
      next: failure
    failure:
      type: end
      outcome: failed
      error:
        code: FAILED
        message: failed
    complete:
      type: end
      outcome: succeeded
      output: {ref: nodes.work.output#/value}
""",
    )

    result = compile_package(package_root)

    assert result.ok


def test_compiler_rejects_schema_paths_without_json_suffix(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.yaml
  outputSchema: schemas/value.json
  entry: done
  nodes:
    done:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
    )
    (package_root / "schemas/value.yaml").write_text(
        '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object"}',
        encoding="utf-8",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "SCHEMA_PATH_INVALID"


def test_compiler_rejects_schema_refs_that_escape_the_package(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: done
  nodes:
    done:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
    )
    (package_root / "schemas/value.json").write_text(
        """\
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$ref": "https://example.invalid/schema.json"
}
""",
        encoding="utf-8",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "SCHEMA_REF_FORBIDDEN"


def test_compiler_rejects_recursive_nested_workflows(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: nested
  nodes:
    nested:
      type: workflow
      workflow: main
      input: {ref: input#}
      next: done
    done:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "NESTED_WORKFLOW_CYCLE"


def test_compiler_rejects_nested_workflow_depth_above_eight(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    (package_root / "workflows").mkdir(parents=True)
    (package_root / "schemas").mkdir()
    (package_root / "schemas/value.json").write_text(
        '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object"}',
        encoding="utf-8",
    )
    workflow_ids = [f"w{index}" for index in range(9)]
    manifest_workflows = "\n".join(
        f"    {workflow_id}: workflows/{workflow_id}.yaml" for workflow_id in workflow_ids
    )
    (package_root / "manifest.yaml").write_text(
        f"""\
apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: nested-depth
  version: 0.1.0
spec:
  workflows:
{manifest_workflows}
  entrypoints: [w0]
  requiredFeatures: [core.nested]
""",
        encoding="utf-8",
    )
    for index, workflow_id in enumerate(workflow_ids):
        next_workflow = workflow_ids[index + 1] if index + 1 < len(workflow_ids) else None
        node = (
            f"""\
    nested:
      type: workflow
      workflow: {next_workflow}
      input: {{ref: input#}}
      next: done
"""
            if next_workflow
            else ""
        )
        entry = "nested" if next_workflow else "done"
        (package_root / f"workflows/{workflow_id}.yaml").write_text(
            f"""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: {workflow_id}
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: {entry}
  nodes:
{node}    done:
      type: end
      outcome: succeeded
      output: {{literal: {{}}}}
""",
            encoding="utf-8",
        )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "NESTED_WORKFLOW_DEPTH"


def test_compiler_rejects_a_missing_nested_workflow_reference(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: nested
  nodes:
    nested:
      type: workflow
      workflow: absent
      input: {ref: input#}
      next: done
    done:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "WORKFLOW_REFERENCE_MISSING"


def test_compiler_resolves_schema_refs_relative_to_the_schema_file() -> None:
    result = compile_package(ROOT / "presets/content-delivery")

    assert result.ok
    assert result.plans["delivery"].input_schema_digest.startswith("sha256:")
    assert result.plans["delivery"].output_schema_digest.startswith("sha256:")


def test_compiler_rejects_a_package_path_that_escapes_the_root(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    (package_root / "manifest.yaml").write_text(
        """apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: path-check
  version: 0.1.0
spec:
  workflows:
    main: ../workflow.yaml
  entrypoints: [main]
  requiredFeatures: []
""",
        encoding="utf-8",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "INVALID_PATH"


def test_compiler_rejects_a_reference_from_only_one_switch_branch(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    (package_root / "workflows").mkdir(parents=True)
    (package_root / "schemas").mkdir()
    (package_root / "manifest.yaml").write_text(
        """apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: branch-dominance
  version: 0.1.0
spec:
  workflows:
    main: workflows/main.yaml
  entrypoints: [main]
  requiredFeatures: [core.call, core.switch]
""",
        encoding="utf-8",
    )
    (package_root / "workflows/main.yaml").write_text(
        """apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: route
  nodes:
    route:
      type: switch
      cases:
        - id: left
          when:
            op: eq
            left: {ref: input#/enabled}
            right: {literal: true}
          next: left
      default: right
    left:
      type: call
      slot: worker
      inputSchema: schemas/value.json
      outputSchema: schemas/value.json
      input: {ref: input#}
      requires:
        capabilities: [data.process@1]
      effects:
        class: none
        actions: []
      next: complete
    right:
      type: call
      slot: worker
      inputSchema: schemas/value.json
      outputSchema: schemas/value.json
      input: {ref: input#}
      requires:
        capabilities: [data.process@1]
      effects:
        class: none
        actions: []
      next: complete
    complete:
      type: end
      outcome: succeeded
      output: {ref: nodes.left.output#/value}
""",
        encoding="utf-8",
    )
    (package_root / "schemas/value.json").write_text(
        """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["value"],
  "properties": {"enabled": {"type": "boolean"}, "value": {"type": "string"}}
}
""",
        encoding="utf-8",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "DATA_REFERENCE_UNAVAILABLE"


def test_compiler_rejects_a_missing_input_pointer(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: work
  nodes:
    work:
      type: call
      slot: worker
      inputSchema: schemas/value.json
      outputSchema: schemas/value.json
      input: {ref: input#/missing}
      requires:
        capabilities: [data.process@1]
      effects:
        class: none
        actions: []
      next: complete
    complete:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "DATA_REFERENCE_MISSING"


def test_compiler_rejects_a_missing_nested_workflow_output_pointer(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    (package_root / "workflows").mkdir(parents=True)
    (package_root / "schemas").mkdir()
    (package_root / "manifest.yaml").write_text(
        """\
apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: nested-output
  version: 0.1.0
spec:
  workflows:
    main: workflows/main.yaml
    child: workflows/child.yaml
  entrypoints: [main]
  requiredFeatures: [core.nested]
""",
        encoding="utf-8",
    )
    (package_root / "schemas/value.json").write_text(
        """\
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {"value": {"type": "string"}}
}
""",
        encoding="utf-8",
    )
    (package_root / "workflows/child.yaml").write_text(
        """\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: child
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: done
  nodes:
    done:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
        encoding="utf-8",
    )
    (package_root / "workflows/main.yaml").write_text(
        """\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: child
  nodes:
    child:
      type: workflow
      workflow: child
      input: {ref: input#}
      next: complete
    complete:
      type: end
      outcome: succeeded
      output: {ref: nodes.child.output#/missing}
""",
        encoding="utf-8",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "DATA_REFERENCE_MISSING"


def test_compiler_rejects_a_business_field_on_an_error_path(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: work
  nodes:
    work:
      type: call
      slot: worker
      inputSchema: schemas/value.json
      outputSchema: schemas/value.json
      input: {ref: input#}
      requires:
        capabilities: [data.process@1]
      effects:
        class: none
        actions: []
      onError: handle-error
      next: complete
    handle-error:
      type: call
      slot: worker
      inputSchema: schemas/value.json
      outputSchema: schemas/value.json
      input: {ref: nodes.work.output#/value}
      requires:
        capabilities: [data.process@1]
      effects:
        class: none
        actions: []
      next: failure
    failure:
      type: end
      outcome: failed
      error:
        code: FAILED
        message: failed
    complete:
      type: end
      outcome: succeeded
      output: {ref: nodes.work.output#/value}
""",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "ERROR_OUTPUT_REFERENCE_INVALID"


def test_compiler_rejects_an_adapter_mismatch_and_plain_secret_reference(tmp_path: Path) -> None:
    binding = tmp_path / "binding.yaml"
    binding.write_text(
        """\
apiVersion: multiverse/v0.1
kind: BindingSet
metadata:
  name: invalid
  version: 0.1.0
spec:
  slots:
    producer:
      adapter: human
      executorRef: example.content-fixture.v1
      config: {}
      secretRefs:
        token: plain-secret
      grants: []
""",
        encoding="utf-8",
    )

    result = compile_package(ROOT / "presets/content-delivery", binding_path=binding)

    assert not result.ok
    assert result.diagnostics[0].code == "INVALID_SPEC"


def test_compiler_rejects_missing_declared_package_resources(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: done
  nodes:
    done:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
    )
    manifest = (package_root / "manifest.yaml").read_text(encoding="utf-8")
    (package_root / "manifest.yaml").write_text(
        manifest.replace(
            "requiredFeatures: [core.nested, core.call]",
            """requiredFeatures: [core.nested, core.call]
  evalSuites: [evals/missing.yaml]
  assets:
    prompt: {path: prompts/missing.md, kind: prompt, format: markdown, version: 1.0.0}""",
        ),
        encoding="utf-8",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "FILE_NOT_FOUND"


def test_compiler_rejects_a_stale_package_lock(tmp_path: Path) -> None:
    package_root = _write_minimal_package(
        tmp_path,
        workflow_text="""\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/value.json
  outputSchema: schemas/value.json
  entry: done
  nodes:
    done:
      type: end
      outcome: succeeded
      output: {literal: {}}
""",
    )
    (package_root / "package.lock.json").write_text(
        '{"files":[],"packageDigest":"sha256:stale"}',
        encoding="utf-8",
    )

    result = compile_package(package_root)

    assert not result.ok
    assert result.diagnostics[0].code == "PACKAGE_LOCK_MISMATCH"


def _write_minimal_package(tmp_path: Path, *, workflow_text: str) -> Path:
    package_root = tmp_path / "package"
    (package_root / "workflows").mkdir(parents=True)
    (package_root / "schemas").mkdir()
    (package_root / "manifest.yaml").write_text(
        """\
apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: test-package
  version: 0.1.0
spec:
  workflows:
    main: workflows/main.yaml
  entrypoints: [main]
  requiredFeatures: [core.nested, core.call]
""",
        encoding="utf-8",
    )
    (package_root / "workflows/main.yaml").write_text(workflow_text, encoding="utf-8")
    (package_root / "schemas/value.json").write_text(
        """\
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {"value": {"type": "string"}}
}
""",
        encoding="utf-8",
    )
    return package_root
