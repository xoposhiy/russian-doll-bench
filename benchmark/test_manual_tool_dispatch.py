from unittest import mock

import benchmark.infrastructure as infra_module


def test_dispatch_manual_tool_returns_error_for_missing_required_args():
    tools = infra_module._make_bound_tools(infra_module.VirtualFileSystem())

    with mock.patch.object(infra_module, "emit_event") as emit_event_mock:
        result, should_stop = infra_module._dispatch_tool(
            "update_file",
            {"filename": "main.py", "str_to_replace": "old"},
            tools,
        )

    assert should_stop is False
    assert "Invalid arguments for tool 'update_file'" in result["error"]
    assert "replacement" in result["error"]
    assert any(
        call.kwargs.get("event_type") == "tool_result"
        and call.kwargs.get("tool_name") == "update_file"
        and call.kwargs.get("error_type") == "invalid_tool_args"
        for call in emit_event_mock.call_args_list
    )


def test_dispatch_manual_tool_returns_error_for_non_object_args():
    tools = infra_module._make_bound_tools(infra_module.VirtualFileSystem())

    with mock.patch.object(infra_module, "emit_event") as emit_event_mock:
        result, should_stop = infra_module._dispatch_tool(
            "write_file",
            ["filename", "main.py"],
            tools,
        )

    assert should_stop is False
    assert result == {"error": "Invalid arguments for tool 'write_file': expected an object, got list."}
    assert any(
        call.kwargs.get("event_type") == "tool_result"
        and call.kwargs.get("tool_name") == "write_file"
        and call.kwargs.get("error_type") == "invalid_tool_args"
        for call in emit_event_mock.call_args_list
    )


def test_bound_tools_create_parent_directories_on_write(tmp_path):
    vfs = infra_module.VirtualFileSystem()
    vfs.root = tmp_path
    tmp_path.mkdir(parents=True, exist_ok=True)
    tools = infra_module._make_bound_tools(vfs)

    result = tools["write_file"]("nested/dir/main.py", "print('ok')")

    assert result == {
        "file": "nested/dir/main.py",
        "operation": "created",
        "new_size": len("print('ok')"),
    }
    assert (tmp_path / "nested" / "dir" / "main.py").read_text(encoding="utf-8") == "print('ok')"


def test_dispatch_manual_tool_converts_tool_exceptions_to_tool_results():
    tools = {"explode": mock.Mock(side_effect=RuntimeError("boom"))}

    with mock.patch.object(infra_module, "emit_event") as emit_event_mock:
        result, should_stop = infra_module._dispatch_tool(
            "explode",
            {},
            tools,
        )

    assert should_stop is False
    assert result == {"error": "Tool 'explode' failed: RuntimeError: boom"}
    assert any(
        call.kwargs.get("event_type") == "tool_result"
        and call.kwargs.get("tool_name") == "explode"
        and call.kwargs.get("error_type") == "tool_runtime_error"
        for call in emit_event_mock.call_args_list
    )
