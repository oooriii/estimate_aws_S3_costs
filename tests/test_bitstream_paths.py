import pytest

from bitstream_paths import parse_bitstream_ref


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        (
            "/bitstream/10256/12046/4/GibertSoteloPujolPayet_2015_Morphology.pdf",
            "/bitstream/10256/12046/4/GibertSoteloPujolPayet_2015_Morphology.pdf",
        ),
        (
            "/bitstream/handle/10256/12046/GibertSoteloPujolPayet_2015_Morphology.pdf?sequence=4",
            "/bitstream/10256/12046/4/GibertSoteloPujolPayet_2015_Morphology.pdf",
        ),
        (
            "//bitstream/10256/4784/1/tjbae.pdf",
            "/bitstream/10256/4784/1/tjbae.pdf",
        ),
        (
            "/bitstream/handle/10256/3066/192.pdf?sequence=1",
            "/bitstream/10256/3066/1/192.pdf",
        ),
        (
            "/bitstream/handle/10256.2/29212/MSVV28_6664.pdf?isAllowed=y&sequence=1",
            "/bitstream/10256.2/29212/1/MSVV28_6664.pdf",
        ),
        (
            "/bitstream/handle/10256.2/7275/ID1_33_TC.pdf;jsessionid=ABC?sequence=1",
            "/bitstream/10256.2/7275/1/ID1_33_TC.pdf",
        ),
        (
            "/bitstream/handle/10256.2/1598/ID1_3285_TC.pdf?sequence=1&amp;isAllowed=y",
            "/bitstream/10256.2/1598/1/ID1_3285_TC.pdf",
        ),
        (
            "/bitstream/10256.2/29921/1/FLMM_02_17.pdf",
            "/bitstream/10256.2/29921/1/FLMM_02_17.pdf",
        ),
    ],
)
def test_parse_bitstream_ref_normalizes_dspace_paths(raw_path, expected):
    ref = parse_bitstream_ref(raw_path)

    assert ref is not None
    assert ref.canonical_path == expected


def test_parse_bitstream_ref_rejects_non_bitstream_paths():
    assert parse_bitstream_ref("/favicon.ico") is None
    assert parse_bitstream_ref("/.within.website/x/cmd/anubis/static/img/pensive.webp") is None
