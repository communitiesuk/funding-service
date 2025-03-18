from typing import get_type_hints

from app.config import DevConfig, LocalConfig, ProdConfig, UatConfig, _SharedConfig


def test_config_subclasses_do_not_have_conflicting_types():
    parent_class_types = get_type_hints(_SharedConfig)

    for subclass in [LocalConfig, DevConfig, UatConfig, ProdConfig]:
        subclass_types = get_type_hints(subclass)

        for attr_name, attr_type in parent_class_types.items():
            assert parent_class_types[attr_name] == subclass_types[attr_name], (
                f"SharedConfig defines {attr_name} as type `{attr_type}` "
                f"but {subclass.__name__} defines it as type `{subclass_types[attr_name]}`"
            )


def test_config_subclasses_do_not_define_new_variables():
    parent_class_types = get_type_hints(_SharedConfig)

    for subclass in [LocalConfig, DevConfig, UatConfig, ProdConfig]:
        subclass_types = get_type_hints(subclass)

        for attr_name in subclass_types.keys():
            assert attr_name in parent_class_types, (
                f"SharedConfig does not define an {attr_name} config variable, but it is present on {subclass.__name__}"
            )
