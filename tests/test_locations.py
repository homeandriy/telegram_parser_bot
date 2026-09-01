import unittest

from telegram_parser.alerts.locations import (
    OBLAST_TYPE,
    RAION_TYPE,
    SPECIAL_CITY_TYPE,
    load_bundled_locations,
    parse_locations_csv,
)


class LocationCsvTests(unittest.TestCase):
    def test_bundled_reference_contains_kyiv_and_rayon_hierarchy(self) -> None:
        locations = load_bundled_locations()
        kyiv = next(location for location in locations if location.uid == 31)
        rayon = next(location for location in locations if location.location_type == RAION_TYPE)

        self.assertGreater(len(locations), 1_500)
        self.assertEqual("м. Київ", kyiv.title)
        self.assertEqual(SPECIAL_CITY_TYPE, kyiv.location_type)
        self.assertIsNotNone(rayon.oblast_uid)
    def test_preserves_oblast_and_raion_hierarchy(self) -> None:
        locations = parse_locations_csv(
            "UID,Назва,Тип\n"
            "1,Київська область,Область\n"
            "2,Бучанський район,Район\n"
            "3,Бучанська громада,Громада\n"
            "31,м. Київ,Місто з спеціальним статусом\n"
        )

        self.assertEqual(locations[0].location_type, OBLAST_TYPE)
        self.assertEqual((locations[1].oblast_uid, locations[1].raion_uid), (1, None))
        self.assertEqual(locations[1].location_type, RAION_TYPE)
        self.assertEqual((locations[2].oblast_uid, locations[2].raion_uid), (1, 2))
        self.assertEqual(locations[3].location_type, SPECIAL_CITY_TYPE)
        self.assertIsNone(locations[3].oblast_uid)


if __name__ == "__main__":
    unittest.main()
