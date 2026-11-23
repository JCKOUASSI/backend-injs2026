from django.test import TestCase

from .duration_format import format_duration_minutes, minutes_to_hours_minutes


class DurationFormatTest(TestCase):

    def test_minutes_to_hours_minutes_normalizes_sixty(self):
        self.assertEqual(minutes_to_hours_minutes(240), (4, 0))
        self.assertEqual(minutes_to_hours_minutes(180), (3, 0))
        self.assertEqual(minutes_to_hours_minutes(220), (3, 40))

    def test_format_duration_minutes_no_invalid_sixty(self):
        self.assertEqual(format_duration_minutes(240), '4h')
        self.assertEqual(format_duration_minutes(180), '3h')
        self.assertEqual(format_duration_minutes(220), '3h 40min')
        self.assertEqual(format_duration_minutes(45), '45min')
        self.assertEqual(format_duration_minutes(0), '0h')
