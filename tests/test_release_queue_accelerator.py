import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_accelerator():
    spec = importlib.util.spec_from_file_location(
        "release_queue_accelerator",
        ROOT / "ops" / "release_queue_accelerator.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_ls_remote_sorts_pull_refs_and_main():
    accelerator = load_accelerator()
    snapshot = accelerator.parse_ls_remote(
        "\n".join(
            [
                "f" * 40 + "\trefs/pull/104/head",
                "a" * 40 + "\trefs/heads/main",
                "b" * 40 + "\trefs/pull/83/head",
            ]
        )
    )

    assert snapshot.main_sha == "a" * 40
    assert [ref.pr for ref in snapshot.pull_refs] == [83, 104]


def test_known_merged_refs_are_not_treated_as_open_blockers():
    accelerator = load_accelerator()

    assert accelerator.classify_ref(83, {83}, {83}) == "merged_or_superseded_ref_visible"
    assert accelerator.classify_ref(104, {83}, {104}) == "priority_ref_visible_metadata_required"
    assert accelerator.classify_ref(46, {83}, {104}) == "backlog_ref_visible_metadata_required"


def test_markdown_reports_priority_metadata_gap():
    accelerator = load_accelerator()
    snapshot = accelerator.parse_ls_remote(
        "\n".join(
            [
                "a" * 40 + "\trefs/heads/main",
                "b" * 40 + "\trefs/pull/83/head",
                "c" * 40 + "\trefs/pull/104/head",
            ]
        )
    )

    markdown = accelerator.render_markdown(
        snapshot,
        source="fixture",
        known_merged={83},
        priority={83, 104},
    )

    assert "Pull refs visible: `2`" in markdown
    assert "| #83 | `bbbbbbbbbbbb` | `merged_or_superseded_ref_visible`" in markdown
    assert "| #104 | `cccccccccccc` | `priority_ref_visible_metadata_required`" in markdown
