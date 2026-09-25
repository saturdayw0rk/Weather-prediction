"""Coordinates of Mongolian cities available in the location selector.

Coordinates are city-centre WGS84 positions (decimal degrees). Open-Meteo snaps
each request to its nearest model grid cell; the dashboard displays both the
requested and the returned grid coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    name: str
    province: str
    latitude: float
    longitude: float


LOCATIONS: dict[str, Location] = {
    loc.name: loc
    for loc in [
        Location("Ulaanbaatar", "Capital", 47.9184, 106.9177),
        Location("Darkhan", "Darkhan-Uul", 49.4867, 105.9228),
        Location("Erdenet", "Orkhon", 49.0278, 104.0444),
        Location("Choibalsan", "Dornod", 48.0703, 114.5071),
        Location("Mörön", "Khövsgöl", 49.6342, 100.1625),
        Location("Khovd", "Khovd", 48.0056, 91.6419),
        Location("Ölgii", "Bayan-Ölgii", 48.9683, 89.9625),
        Location("Ulaangom", "Uvs", 49.9811, 92.0667),
        Location("Uliastai", "Zavkhan", 47.7417, 96.8444),
        Location("Altai", "Govi-Altai", 46.3722, 96.2583),
        Location("Bayankhongor", "Bayankhongor", 46.1944, 100.7181),
        Location("Arvaikheer", "Övörkhangai", 46.2639, 102.7750),
        Location("Kharkhorin", "Övörkhangai", 47.1975, 102.8238),
        Location("Tsetserleg", "Arkhangai", 47.4769, 101.4503),
        Location("Bulgan", "Bulgan", 48.8125, 103.5347),
        Location("Sükhbaatar", "Selenge", 50.2314, 106.2078),
        Location("Zuunmod", "Töv", 47.7069, 106.9528),
        Location("Chinggis (Öndörkhaan)", "Khentii", 47.3194, 110.6556),
        Location("Baruun-Urt", "Sükhbaatar", 46.6806, 113.2792),
        Location("Sainshand", "Dornogovi", 44.8917, 110.1361),
        Location("Choir", "Govisümber", 46.3611, 108.3611),
        Location("Mandalgovi", "Dundgovi", 45.7625, 106.2708),
        Location("Dalanzadgad", "Ömnögovi", 43.5708, 104.4250),
    ]
}

# ICAO identifiers of Mongolian aerodromes that may publish METAR reports.
# Not all of them report to the international feed; the service picks the
# nearest station that actually returned a recent report.
METAR_STATIONS: tuple[str, ...] = (
    "ZMUB",  # Ulaanbaatar Buyant-Ukhaa (old airport, in the city)
    "ZMCK",  # Chinggis Khaan International (Khöshig valley, ~30 km south)
    "ZMDN",  # Darkhan
    "ZMEN",  # Erdenet
    "ZMCD",  # Choibalsan
    "ZMMN",  # Mörön
    "ZMKD",  # Khovd
    "ZMUL",  # Ölgii
    "ZMUG",  # Ulaangom
    "ZMDZ",  # Dalanzadgad
    "ZMBH",  # Bayankhongor
    "ZMAT",  # Altai
    "ZMAH",  # Arvaikheer
    "ZMBN",  # Bulgan
    "ZMSH",  # Sainshand
    "ZMBU",  # Baruun-Urt
    "ZMUH",  # Öndörkhaan
    "ZMTG",  # Tosontsengel
    "ZMDA",  # Uliastai (Donoi)
)
