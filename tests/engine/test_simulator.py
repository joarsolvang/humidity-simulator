import pandas as pd
import pytest

from humidity_simulator.engine.simulator import (
    InternalHumiditySimulator,
    UnitConsistencyError,
)
from humidity_simulator.models import HumiditySource


class TestUnitValidation:
    """Tests for unit consistency validation."""

    def test_valid_metric_units(self) -> None:
        """Simulator accepts all metric units."""
        sim = InternalHumiditySimulator(
            surface_area=100,
            surface_area_unit="m2",
            ceiling_height=3,
            ceiling_height_unit="m",
            internal_temperature=20,
            internal_temperature_unit="c",
            air_changes_per_hour=0.1,
        )
        assert sim.surface_area == 100
        assert sim.ceiling_height == 3
        assert sim.internal_temperature == 20

    def test_valid_metric_units_kelvin(self) -> None:
        """Simulator accepts metric units with Kelvin temperature."""
        sim = InternalHumiditySimulator(
            surface_area=100,
            surface_area_unit="m2",
            ceiling_height=3,
            ceiling_height_unit="m",
            internal_temperature=293,
            internal_temperature_unit="k",
            air_changes_per_hour=0.1,
        )
        assert sim.internal_temperature_unit == "k"

    def test_valid_imperial_units(self) -> None:
        """Simulator accepts all imperial units."""
        sim = InternalHumiditySimulator(
            surface_area=1000,
            surface_area_unit="ft2",
            ceiling_height=10,
            ceiling_height_unit="ft",
            internal_temperature=68,
            internal_temperature_unit="f",
            air_changes_per_hour=0.1,
        )
        assert sim.surface_area == 1000
        assert sim.ceiling_height == 10
        assert sim.internal_temperature == 68

    def test_mixed_area_metric_height_imperial_raises(self) -> None:
        """Mixing metric area with imperial height raises error."""
        with pytest.raises(UnitConsistencyError, match="Inconsistent unit systems"):
            InternalHumiditySimulator(
                surface_area=100,
                surface_area_unit="m2",
                ceiling_height=10,
                ceiling_height_unit="ft",
                internal_temperature=20,
                internal_temperature_unit="c",
                air_changes_per_hour=0.1,
            )

    def test_mixed_area_imperial_height_metric_raises(self) -> None:
        """Mixing imperial area with metric height raises error."""
        with pytest.raises(UnitConsistencyError, match="Inconsistent unit systems"):
            InternalHumiditySimulator(
                surface_area=1000,
                surface_area_unit="ft2",
                ceiling_height=3,
                ceiling_height_unit="m",
                internal_temperature=68,
                internal_temperature_unit="f",
                air_changes_per_hour=0.1,
            )

    def test_mixed_metric_dimensions_imperial_temperature_raises(self) -> None:
        """Mixing metric dimensions with imperial temperature raises error."""
        with pytest.raises(UnitConsistencyError, match="Inconsistent unit systems"):
            InternalHumiditySimulator(
                surface_area=100,
                surface_area_unit="m2",
                ceiling_height=3,
                ceiling_height_unit="m",
                internal_temperature=68,
                internal_temperature_unit="f",
                air_changes_per_hour=0.1,
            )

    def test_mixed_imperial_dimensions_metric_temperature_raises(self) -> None:
        """Mixing imperial dimensions with metric temperature raises error."""
        with pytest.raises(UnitConsistencyError, match="Inconsistent unit systems"):
            InternalHumiditySimulator(
                surface_area=1000,
                surface_area_unit="ft2",
                ceiling_height=10,
                ceiling_height_unit="ft",
                internal_temperature=20,
                internal_temperature_unit="c",
                air_changes_per_hour=0.1,
            )

    def test_error_message_contains_unit_details(self) -> None:
        """Error message includes which units are metric vs imperial."""
        with pytest.raises(UnitConsistencyError) as exc_info:
            InternalHumiditySimulator(
                surface_area=100,
                surface_area_unit="m2",
                ceiling_height=10,
                ceiling_height_unit="ft",
                internal_temperature=20,
                internal_temperature_unit="c",
                air_changes_per_hour=0.1,
            )
        error_message = str(exc_info.value)
        assert "surface_area_unit=metric" in error_message
        assert "ceiling_height_unit=imperial" in error_message
        assert "temperature_unit=metric" in error_message


class TestBuildEmissionsDataframe:
    """Tests for _build_emissions_dataframe method."""

    @pytest.mark.parametrize(
        ("timestamps", "timestamp_format", "source_timezone", "expected_output_tz", "expected_log"),
        [
            pytest.param(
                ["2024-01-01 08:00", "2024-01-01 09:00"],
                "%Y-%m-%d %H:%M",
                "UTC",
                "UTC",
                None,  # No warning for naive timestamps
                id="naive_utc_to_utc",
            ),
            pytest.param(
                ["2024-01-01 08:00+00:00", "2024-01-01 09:00+00:00"],
                "%Y-%m-%d %H:%M%z",
                "UTC",
                "UTC",
                "has timezone info in timestamp format and also specifies timezone attribute",
                id="aware_utc_to_utc",
            ),
            pytest.param(
                ["2024-01-01 08:00+05:00", "2024-01-01 09:00+05:00"],
                "%Y-%m-%d %H:%M%z",
                "UTC",
                "UTC",
                "has timezone info in timestamp format and also specifies timezone attribute",
                id="aware_plus5_to_utc",
            ),
        ],
    )
    def test_timezone_handling(
        self,
        simulator: InternalHumiditySimulator,
        caplog: pytest.LogCaptureFixture,
        timestamps: list[str],
        timestamp_format: str,
        source_timezone: str,
        expected_output_tz: str,
        expected_log: str | None,
    ) -> None:
        """Test that output timezone matches expected timezone for various input configurations."""
        source = HumiditySource(
            name="test_source",
            max_emissions_rate_unit="g/h",
            timestamps=timestamps,
            timestamp_format=timestamp_format,
            timezone=source_timezone,
            values=[100.0, 200.0],
            values_unit="g/h",
        )

        df = simulator._build_emissions_dataframe([source], time_resolution=pd.Timedelta(hours=1))

        assert str(df.index.tz) == expected_output_tz

        if expected_log is not None:
            assert expected_log in caplog.text
        else:
            assert caplog.text == ""

    @pytest.mark.parametrize(
        ("source_tz", "source_timestamps", "target_tz", "expected_first_hour"),
        [
            pytest.param(
                "UTC",
                ["2024-01-01 12:00", "2024-01-01 13:00"],
                "UTC",
                12,
                id="utc_to_utc_no_conversion",
            ),
            pytest.param(
                "America/New_York",
                ["2024-01-01 07:00", "2024-01-01 08:00"],
                "UTC",
                12,
                id="est_to_utc_adds_5_hours",
            ),
            pytest.param(
                "Europe/London",
                ["2024-01-01 12:00", "2024-01-01 13:00"],
                "America/New_York",
                7,
                id="london_to_est_subtracts_5_hours",
            ),
        ],
    )
    def test_timezone_conversion(
        self,
        simulator: InternalHumiditySimulator,
        source_tz: str,
        source_timestamps: list[str],
        target_tz: str,
        expected_first_hour: int,
    ) -> None:
        """Test that timestamps are correctly converted to the target timezone."""
        source = HumiditySource(
            name="test_source",
            max_emissions_rate_unit="g/h",
            timestamps=source_timestamps,
            timestamp_format="%Y-%m-%d %H:%M",
            timezone=source_tz,
            values=[100.0, 100.0],
            values_unit="g/h",
        )

        df = simulator._build_emissions_dataframe(
            [source],
            time_resolution=pd.Timedelta(hours=1),
            target_timezone=target_tz,
        )

        assert df.index[0].hour == expected_first_hour
        assert str(df.index.tz) == target_tz

    def test_resamples_to_specified_time_resolution(self, simulator: InternalHumiditySimulator) -> None:
        """Data is resampled to the specified time resolution."""
        # Source with 1-hour intervals
        source_hourly = HumiditySource(
            name="hourly",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 08:00", "2024-01-01 09:00", "2024-01-01 10:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[100.0, 100.0, 100.0],
            values_unit="g/h",
        )
        # Source with 30-minute intervals
        source_half_hourly = HumiditySource(
            name="half_hourly",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 08:00", "2024-01-01 08:30", "2024-01-01 09:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[200.0, 200.0, 200.0],
            values_unit="g/h",
        )

        df = simulator._build_emissions_dataframe(
            [source_hourly, source_half_hourly],
            time_resolution=pd.Timedelta(minutes=30),
        )

        # Should have 5 rows: 08:00, 08:30, 09:00, 09:30, 10:00
        assert len(df) == 5
        # Check time delta is 30 minutes
        time_deltas = df.index.to_series().diff().dropna()
        assert all(delta == pd.Timedelta(minutes=30) for delta in time_deltas)

    def test_default_time_resolution_is_30_minutes(self, simulator: InternalHumiditySimulator) -> None:
        """Default time resolution is 30 minutes."""
        source = HumiditySource(
            name="test_source",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 08:00", "2024-01-01 10:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[100.0, 100.0],
            values_unit="g/h",
        )

        df = simulator._build_emissions_dataframe([source])

        # Should have 5 rows: 08:00, 08:30, 09:00, 09:30, 10:00
        assert len(df) == 5
        time_deltas = df.index.to_series().diff().dropna()
        assert all(delta == pd.Timedelta(minutes=30) for delta in time_deltas)

    def test_forward_fills_missing_values(self, simulator: InternalHumiditySimulator) -> None:
        """Missing values are forward-filled after resampling."""
        # Source with 1-hour intervals
        source_hourly = HumiditySource(
            name="hourly",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 08:00", "2024-01-01 09:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[100.0, 200.0],
            values_unit="g/h",
        )
        # Source with 30-minute intervals
        source_half_hourly = HumiditySource(
            name="half_hourly",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 08:00", "2024-01-01 08:30", "2024-01-01 09:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[50.0, 75.0, 100.0],
            values_unit="g/h",
        )

        df = simulator._build_emissions_dataframe(
            [source_hourly, source_half_hourly],
            time_resolution=pd.Timedelta(minutes=30),
        )

        # At 08:30, hourly source should be forward-filled from 08:00 value
        row_0830 = df.loc[df.index == "2024-01-01 08:30:00+00:00"]
        assert row_0830["hourly (g/h)"].iloc[0] == 100.0  # Forward-filled from 08:00
        assert row_0830["half_hourly (g/h)"].iloc[0] == 75.0  # Actual value

    def test_converts_values_to_grams_per_hour(self, simulator: InternalHumiditySimulator) -> None:
        """Values are converted to g/h regardless of input unit."""
        source_kg = HumiditySource(
            name="kg_source",
            max_emissions_rate_unit="kg/h",
            timestamps=["2024-01-01 08:00", "2024-01-01 09:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[1.0, 2.0],  # 1 kg/h = 1000 g/h
            values_unit="kg/h",
        )

        df = simulator._build_emissions_dataframe([source_kg], time_resolution=pd.Timedelta(hours=1))

        assert list(df["kg_source (g/h)"]) == [1000.0, 2000.0]

    def test_leading_nans_filled_with_zero(self, simulator: InternalHumiditySimulator) -> None:
        """Sources that start later have leading values filled with zero."""
        source_early = HumiditySource(
            name="early",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 08:00", "2024-01-01 09:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[100.0, 100.0],
            values_unit="g/h",
        )
        source_late = HumiditySource(
            name="late",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 09:00", "2024-01-01 10:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[200.0, 200.0],
            values_unit="g/h",
        )

        df = simulator._build_emissions_dataframe(
            [source_early, source_late],
            time_resolution=pd.Timedelta(hours=1),
        )

        # At 08:00, late source should be 0 (hasn't started yet)
        row_0800 = df.loc[df.index == "2024-01-01 08:00:00+00:00"]
        assert row_0800["early (g/h)"].iloc[0] == 100.0
        assert row_0800["late (g/h)"].iloc[0] == 0.0

    def test_continuous_timeseries_with_gaps(self, simulator: InternalHumiditySimulator) -> None:
        """Gaps between sources are filled with zeros at the specified time resolution."""
        morning_source = HumiditySource(
            name="morning",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 08:00", "2024-01-01 09:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[100.0, 100.0],
            values_unit="g/h",
        )
        # 3-hour gap between sources
        afternoon_source = HumiditySource(
            name="afternoon",
            max_emissions_rate_unit="g/h",
            timestamps=["2024-01-01 12:00", "2024-01-01 13:00"],
            timestamp_format="%Y-%m-%d %H:%M",
            timezone="UTC",
            values=[200.0, 200.0],
            values_unit="g/h",
        )

        df = simulator._build_emissions_dataframe(
            [morning_source, afternoon_source],
            time_resolution=pd.Timedelta(hours=1),
        )

        # Should have continuous hourly timestamps from 08:00 to 13:00 (6 rows)
        assert len(df) == 6
        expected_hours = [8, 9, 10, 11, 12, 13]
        assert [ts.hour for ts in df.index] == expected_hours

        # Gap hours (10:00, 11:00) should have zeros for both sources
        row_1000 = df.loc[df.index == "2024-01-01 10:00:00+00:00"]
        assert row_1000["morning (g/h)"].iloc[0] == 0.0
        assert row_1000["afternoon (g/h)"].iloc[0] == 0.0

        row_1100 = df.loc[df.index == "2024-01-01 11:00:00+00:00"]
        assert row_1100["morning (g/h)"].iloc[0] == 0.0
        assert row_1100["afternoon (g/h)"].iloc[0] == 0.0
