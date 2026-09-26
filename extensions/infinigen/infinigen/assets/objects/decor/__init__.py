__all__ = ["AquariumTankFactory", "UrbanLakeFactory"]


def __getattr__(name):
    """Keep legacy package exports without importing aquarium dependencies eagerly."""
    if name == "AquariumTankFactory":
        from .aquarium_tank import AquariumTankFactory

        return AquariumTankFactory
    if name == "UrbanLakeFactory":
        from .urban_lake import UrbanLakeFactory

        return UrbanLakeFactory
    raise AttributeError(name)
