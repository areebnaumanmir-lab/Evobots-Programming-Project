"""The capital explorer loads without errors, makes no requests and shows §10's values."""

from pathlib import Path

import pytest

EXPLORER_PATH = Path(__file__).resolve().parents[1] / "tools/capital_explorer.html"


@pytest.fixture
def explorer_page(chromium_browser):
    page = chromium_browser.new_page()
    console_errors, requests = [], []
    page.on("console", lambda message: message.type == "error" and console_errors.append(message))
    page.on("pageerror", lambda error: console_errors.append(error))
    page.on("request", lambda request: requests.append(request.url))
    page.goto(EXPLORER_PATH.as_uri())
    yield page
    page.close()
    assert console_errors == []
    assert requests == [EXPLORER_PATH.as_uri()]


def set_capital(page, capital_usd):
    index = (capital_usd - 250_000) // 50_000
    page.eval_on_selector(
        "#capital",
        "(slider, index) => { slider.value = index; slider.dispatchEvent(new Event('input')); }",
        index,
    )


def test_defaults(explorer_page):
    assert explorer_page.text_content("#capital-value") == "$1,500,000"
    assert explorer_page.text_content("#budget-value") == "2.0%"
    assert explorer_page.text_content("#scale") == "100.0%"
    assert explorer_page.text_content("#fixed_cost") == "$0.203"
    assert explorer_page.text_content("#floor") == "off"
    assert explorer_page.text_content("#warnings") == ""


@pytest.mark.parametrize(
    ("capital_usd", "scale", "cost", "worst_full", "floor", "worst_point_in_time", "warnings"),
    [
        (1_500_000, "100.0%", "$0.203", "32.3%", "$1,000,000", "24.6%", 0),
        (1_050_000, "75.3%", "$0.270", "34.7%", "$700,000", "34.5%", 1),
        (5_000_000, "100.0%", "$0.203", "9.7%", "$3,333,333", "8.2%", 2),
    ],
)
def test_section_10_values_with_the_two_thirds_floor(
    explorer_page, capital_usd, scale, cost, worst_full, floor, worst_point_in_time, warnings
):
    explorer_page.click("a.choice[data-group=floor][data-index='1']")
    set_capital(explorer_page, capital_usd)
    assert explorer_page.text_content("#scale") == scale
    assert explorer_page.text_content("#fixed_cost") == cost
    assert explorer_page.text_content("#worst_full") == worst_full
    assert explorer_page.text_content("#floor") == floor
    assert explorer_page.text_content("#headroom") == "33.3%"
    assert explorer_page.text_content("#worst_point_in_time") == worst_point_in_time
    assert explorer_page.locator("#warnings p").count() == warnings


def test_absolute_floor_too_close_is_rejected(explorer_page):
    explorer_page.click("a.choice[data-group=floor][data-index='2']")
    set_capital(explorer_page, 1_050_000)
    assert explorer_page.text_content("#floor") == "off"
    assert explorer_page.locator("#warnings p").first.text_content().startswith("Floor rejected")


def test_page_has_no_formulas_in_its_script():
    script = EXPLORER_PATH.read_text(encoding="utf-8").split("<script>")[1]
    for operator in ("Math.", " * ", " / ", "parseFloat"):
        assert operator not in script
