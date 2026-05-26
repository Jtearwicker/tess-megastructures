"""Tests for tess_megastructures.utils.paths."""

from __future__ import annotations

import pytest

from tess_megastructures.utils import paths as paths_mod


class TestRepoRoot:
    def test_finds_repo_root(self):
        root = paths_mod.repo_root()
        assert (root / "pyproject.toml").is_file()

    def test_configs_dir(self):
        assert paths_mod.configs_dir() == paths_mod.repo_root() / "configs"
        assert paths_mod.configs_dir().is_dir()

    def test_docs_dir(self):
        assert paths_mod.docs_dir() == paths_mod.repo_root() / "docs"


class TestLoadPaths:
    def test_loads_explicit_file(self, tmp_path):
        f = tmp_path / "paths.yaml"
        f.write_text(
            "doyle2024_catalog: /mnt/primary/TESS/catalogs/doyle2024/targets.dat.gz\n"
            "xml_dir: /mnt/buf0/jearwicker/xml\n"
        )
        result = paths_mod.load_paths(f)
        assert result["doyle2024_catalog"].endswith("targets.dat.gz")
        assert result["xml_dir"] == "/mnt/buf0/jearwicker/xml"

    def test_missing_file_raises_with_helpful_message(self, tmp_path):
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError) as exc:
            paths_mod.load_paths(missing)
        # Error should point at the copy-from-example fix
        assert "paths.example.yaml" in str(exc.value)

    def test_empty_file_returns_empty_dict(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        assert paths_mod.load_paths(f) == {}

    def test_non_mapping_raises(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("- just\n- a\n- list\n")
        with pytest.raises(ValueError):
            paths_mod.load_paths(f)

    def test_default_path_is_configs_paths_yaml(self, tmp_path, monkeypatch):
        # Point configs_dir at a temp dir holding a paths.yaml, confirm default resolves there
        fake_configs = tmp_path / "configs"
        fake_configs.mkdir()
        (fake_configs / "paths.yaml").write_text("output_dir: /tmp/out\n")
        monkeypatch.setattr(paths_mod, "configs_dir", lambda: fake_configs)
        result = paths_mod.load_paths()
        assert result["output_dir"] == "/tmp/out"
