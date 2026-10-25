"""Release journeys exercise real navigation, form posts and visible state."""

import re
from uuid import uuid4

from playwright.sync_api import Page, expect


def create_prompt(page: Page, title: str, body: str = "Helpful text") -> str:
    page.get_by_role("link", name="New prompt", exact=True).click()
    page.get_by_label("Title", exact=True).fill(title)
    page.get_by_label("Prompt body", exact=True).fill(body)
    page.get_by_role("button", name="Create prompt", exact=True).click()
    expect(page.locator("#detail-panel h1")).to_have_text(title)
    expect(page.locator("#library-panel")).to_be_visible()
    return page.locator("[data-prompt-id]").get_attribute("data-prompt-id") or ""


def test_create_favourite_rename_history_modal_delete_and_direct_link(app_page: Page):
    page = app_page
    title = "Prompt " + uuid4().hex
    identity = create_prompt(page, title)
    item = page.locator(f'[data-item-id="{identity}"]')
    page.get_by_role("button", name="Add to favourites", exact=True).click()
    expect(page.get_by_role("button", name="Remove from favourites", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(item.locator(".favourite")).to_be_visible()
    page.locator("#detail-panel").get_by_role("link", name="Edit", exact=True).click()
    renamed = title + " renamed"
    page.get_by_label("Title", exact=True).fill(renamed)
    page.get_by_label("Prompt body", exact=True).fill("Second version")
    page.get_by_role("button", name="Save prompt", exact=True).click()
    expect(item).to_contain_text(renamed)
    expect(page.locator("#detail-panel h1")).to_have_text(renamed)
    page.locator("#version-history summary").click()
    expect(page.locator("#version-history")).to_have_attribute("open", "")
    page.locator("#version-history summary").click()
    expect(page.locator("#version-history")).not_to_have_attribute("open", "")
    page.locator("#version-history summary").click()
    page.get_by_role("button", name="Clear version history", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.locator("#confirm-accept").click()
    expect(page.locator("#version-history summary")).to_have_text("Version history (0)")
    page.reload()
    expect(page.locator("#library-panel")).to_be_visible()
    expect(page.locator("#detail-panel h1")).to_have_text(renamed)
    page.locator("#detail-panel").get_by_role("button", name="Delete", exact=True).click()
    page.get_by_role("dialog").get_by_role("button", name="Cancel", exact=True).click()
    expect(item).to_be_visible()
    page.locator("#detail-panel").get_by_role("button", name="Delete", exact=True).click()
    page.locator("#confirm-accept").click()
    expect(item).to_have_count(0)
    expect(page.locator("#library-panel")).to_be_visible()


def test_sidebar_icons_theme_and_help_literals(app_page: Page):
    page = app_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.locator("#sidebar-toggle").click()
    expect(page.locator("#sidebar-toggle")).to_have_attribute("aria-expanded", "false")
    for selector in ["#theme-toggle", "#sidebar-toggle", ".nav-bottom a"]:
        for element in page.locator(selector).all():
            expect(element).to_be_visible()
            bounds = element.bounding_box()
            assert bounds is not None
            assert bounds["width"] >= 40
            assert bounds["height"] >= 40
    before = page.locator("html").get_attribute("data-theme")
    page.locator("#theme-toggle").click()
    expect(page.locator("html")).not_to_have_attribute("data-theme", before or "light")
    page.locator("#sidebar").get_by_role("link", name="Help", exact=True).click()
    expect(page.locator("#main")).to_contain_text("{{TOPIC}}")
    expect(page.locator("#main")).to_contain_text("{{stage_1_output}}")
    page.locator("#sidebar").get_by_role("link", name="About", exact=True).click()
    expect(page.locator("#main")).to_contain_text("1.0.0")
    expect(page.locator("#main")).to_contain_text("GPL")


def test_workflow_composition_order_and_guided_run(app_page: Page):
    page = app_page
    title = "Source " + uuid4().hex
    create_prompt(page, title, "Research {{TOPIC}}")
    page.get_by_role("link", name="New workflow", exact=True).click()
    name = "Workflow " + uuid4().hex
    page.get_by_label("Name", exact=True).fill(name)
    page.get_by_role("button", name="Create workflow", exact=True).click()
    source_form = page.locator("form[data-stage-source]")
    source_form.get_by_label("Source", exact=True).select_option(label=title)
    source_form.get_by_label("Stage title", exact=True).fill("Research")
    source_form.get_by_role("button", name="Add stage", exact=True).click()
    expect(page.locator(".stage-card h3").filter(has_text="Research")).to_be_visible()
    if not source_form.is_visible():
        page.locator("#add-stage summary").click()
    source_form.get_by_label("Stage title", exact=True).fill("Independent")
    source_form.get_by_label("Body", exact=True).fill("Explain {{TOPIC}}")
    source_form.get_by_role("button", name="Add stage", exact=True).click()
    expect(page.locator(".stage-card h3").filter(has_text="Independent")).to_be_visible()
    page.get_by_role("button", name="Move Independent up", exact=True).click()
    expect(page.locator(".stage-card h3").first).to_have_text("1. Independent")
    page.get_by_role("button", name="Move Independent down", exact=True).click()
    expect(page.locator(".stage-card h3").first).to_have_text("1. Research")
    page.get_by_label("TOPIC", exact=True).fill("SQLite")
    page.get_by_role("button", name="Start guided run", exact=True).click()
    page.wait_for_url(re.compile(r"/workflows/runs/"))
    expect(page.locator("#run-input")).to_have_value("Research SQLite")
    page.get_by_label("Stage output", exact=True).fill("Research output")
    page.get_by_role("button", name="Save output and continue", exact=True).click()
    expect(page.locator("#run-input")).to_have_value("Explain SQLite")
    page.get_by_label("Stage output", exact=True).fill("Final output")
    page.get_by_role("button", name="Save output and complete run", exact=True).click()
    expect(page.locator("#detail-panel")).to_contain_text("All stage outputs have been saved.")
    page.reload()
    expect(page.locator("#library-panel")).to_be_visible()
    expect(page.locator("#detail-panel")).to_contain_text("All stage outputs have been saved.")


def test_search_and_narrow_layout_keep_detail_and_library_visible(app_page: Page):
    page = app_page
    name = "Narrow " + uuid4().hex
    create_prompt(page, name)
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator("#library-panel")).to_be_visible()
    expect(page.locator("#detail-panel h1")).to_have_text(name)
    page.get_by_role("searchbox", name="Search prompts and workflows").fill(name)
    expect(page.locator(".library-item")).to_have_count(1)
    expect(page.locator("#detail-panel h1")).to_have_text(name)
    expect(page).to_have_url(re.compile(r"q="))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_settings_backups_tabs_and_empty_state(app_page: Page):
    page = app_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.get_by_role("link", name="Settings", exact=True).click()
    expect(page.get_by_role("tab", name="Statuses", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    page.get_by_role("tab", name="Categories", exact=True).click()
    expect(page.get_by_role("tabpanel", name="Categories")).to_be_visible()
    expect(page.get_by_role("tab", name="Categories", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    page.get_by_role("tab", name="Storage and access", exact=True).click()
    expect(page.get_by_role("tabpanel", name="Storage and access")).to_be_visible()
    page.locator("#sidebar").get_by_role("link", name="Backups", exact=True).click()
    page.get_by_role("tab", name="Remote configuration", exact=True).click()
    expect(page.get_by_role("tabpanel", name="Remote configuration")).to_be_visible()
    page.get_by_role("tab", name="Manual transfer", exact=True).click()
    expect(page.get_by_role("tabpanel", name="Manual transfer")).to_be_visible()
    page.get_by_role("link", name="Library", exact=True).click()
    panel = page.locator("#detail-panel .empty-detail")
    expect(panel).to_be_visible()
    bounds = panel.bounding_box()
    detail_bounds = page.locator("#detail-panel").bounding_box()
    assert bounds is not None
    assert detail_bounds is not None
    assert bounds["width"] < detail_bounds["width"] * 0.7
    detail_center = detail_bounds["x"] + detail_bounds["width"] / 2
    panel_center = bounds["x"] + bounds["width"] / 2
    assert abs(panel_center - detail_center) < 3
