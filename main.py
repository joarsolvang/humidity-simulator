"""Example usage of the humidity simulator."""

from datetime import datetime

from humidity_simulator.engine.simulator import InternalHumiditySimulator
from humidity_simulator.models import HumiditySource


def main() -> None:
    """Run an example humidity simulation."""
    # Create a simulator for a room
    # 25 m² floor area, 2.5m ceiling height, 20°C internal temperature
    simulator = InternalHumiditySimulator(
        surface_area=25,
        surface_area_unit="m2",
        ceiling_height=2.5,
        ceiling_height_unit="m",
        internal_temperature=20,
        internal_temperature_unit="c",
    )

    print(f"Room volume: {simulator.volume_m3:.1f} m³")
    print(f"Internal temperature: {simulator.temperature_celsius:.1f}°C")
    print()

    # Define humidity sources
    # Shower: high emissions for 15 minutes in the morning
    shower = HumiditySource(
        name="shower",
        max_emissions_rate_unit="g/h",
        timestamps=[
            "2024-01-01 07:00",
            "2024-01-01 07:15",
            "2024-01-01 07:30",
            "2024-01-01 08:00",
            "2024-01-01 09:00",
            "2024-01-01 10:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[0.0, 400.0, 200.0, 0.0, 0.0, 0.0],  # g/h emission rate
        values_unit="g/h",
    )

    # Breathing: constant low emissions from occupants
    breathing = HumiditySource(
        name="breathing",
        max_emissions_rate_unit="g/h",
        timestamps=[
            "2024-01-01 07:00",
            "2024-01-01 08:00",
            "2024-01-01 09:00",
            "2024-01-01 10:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[40.0, 40.0, 40.0, 40.0],  # ~40 g/h per person
        values_unit="g/h",
    )

    ventilation = HumiditySource(
        name="ventilation",
        max_emissions_rate_unit="g/h",
        timestamps=[
            "2024-01-01 09:00",
            "2024-01-01 17:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[-40.0, -40.0],  # ~40 g/h per person
        values_unit="g/h",
    )

    # Cooking: emissions during breakfast
    cooking = HumiditySource(
        name="cooking",
        max_emissions_rate_unit="g/h",
        timestamps=[
            "2024-01-01 07:00",
            "2024-01-01 07:30",
            "2024-01-01 08:00",
            "2024-01-01 08:30",
            "2024-01-01 09:00",
            "2024-01-01 10:00",
        ],
        timestamp_format="%Y-%m-%d %H:%M",
        timezone="UTC",
        values=[0.0, 150.0, 100.0, 0.0, 0.0, 0.0],
        values_unit="g/h",
    )

    # Run simulation starting at 50% relative humidity
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    plot_name = f"humidity_simulation_{timestamp_str}"

    result = simulator.simulate(
        starting_relative_humidity=50,
        humidity_sources=[shower, breathing, cooking, ventilation],
        plot_results=True,
        plot_name=plot_name,
    )

    # Print results
    print("Simulation Results:")
    print("-" * 60)
    print(f"{'Timestamp':<20} {'RH (%)':<12} {'AH (g/m³)':<12}")
    print("-" * 60)

    for ts, rh, ah in zip(
        result.timestamps,
        result.relative_humidity,
        result.absolute_humidity,
        strict=True,
    ):
        print(f"{ts:<20} {rh:<12.1f} {ah:<12.4f}")

    print("-" * 60)
    print(f"Peak relative humidity: {max(result.relative_humidity):.1f}%")
    print(f"Peak absolute humidity: {max(result.absolute_humidity):.4f} g/m³")
    print()
    print(f"Plot saved to: outputs/{plot_name}.png")


if __name__ == "__main__":
    main()
