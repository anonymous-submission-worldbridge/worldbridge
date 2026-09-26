"""Production procedural assets for urban and industrial scenes."""

from .factory_building import (
    FACTORY_REFERENCES,
    FACTORY_VARIANTS,
    FactoryBuildingFactory,
    make_factory_materials,
)

__all__ = [
    "FACTORY_REFERENCES",
    "FACTORY_VARIANTS",
    "FactoryBuildingFactory",
    "make_factory_materials",
]
