from shapely.geometry import shape, Point
from shapely.validation import make_valid
from typing import Dict, Any, Tuple
import math


class BoundaryValidator:
    @staticmethod
    def validate_geometry(geometry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Проверка целостности геометрии."""
        try:
            geom = shape(geometry_data)
            if not geom.is_valid:
                try:
                    geom = make_valid(geom)
                except Exception as make_valid_err:
                    return {
                        "valid": False,
                        "error": "Invalid geometry",
                        "details": str(make_valid_err),
                    }
                return {"valid": True, "repaired": True}
            return {"valid": True}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    @staticmethod
    def point_within_polygon(
        point_coords: Tuple[float, float], polygon_data: Dict[str, Any]
    ) -> bool:
        """Проверяет, находится ли точка внутри полигона. point_coords = (lat, lon)."""
        try:
            point = Point(point_coords[1], point_coords[0])  # (lon, lat) для Shapely
            polygon = shape(polygon_data)
            if not polygon.is_valid:
                polygon = make_valid(polygon)
            return polygon.contains(point)
        except Exception as e:
            return False

    @staticmethod
    def calculate_distance(
        point1: Tuple[float, float], point2: Tuple[float, float]
    ) -> float:
        """Расчёт расстояния между точками в км (формула гаверсинусов). (lat, lon)."""
        R = 6371  # радиус Земли в км
        lat1, lon1 = math.radians(point1[0]), math.radians(point1[1])
        lat2, lon2 = math.radians(point2[0]), math.radians(point2[1])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c
