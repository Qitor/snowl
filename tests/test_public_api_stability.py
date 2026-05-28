"""Public API stability test — validates __all__ exports are complete and importable."""


def test_core_all_exports_importable():
    import snowl.core
    for name in snowl.core.__all__:
        assert hasattr(snowl.core, name), f"snowl.core.{name} listed in __all__ but not found"
        assert getattr(snowl.core, name) is not None, f"snowl.core.{name} is None"
    assert len(snowl.core.__all__) == 82  # Canary: update when API changes intentionally


def test_toplevel_all_exports_importable():
    import snowl
    for name in snowl.__all__:
        assert hasattr(snowl, name), f"snowl.{name} listed in __all__ but not found"
        assert getattr(snowl, name) is not None, f"snowl.{name} is None"
    assert len(snowl.__all__) == 28  # Canary: update when API changes intentionally
