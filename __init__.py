# -*- coding: utf-8 -*-
"""
UWorld Question ID Extractor
Extracts UWorld question IDs from Anki card tags.

Features:
- Tools menu: extract IDs from current deck.
- Browser:
    - Edit menu + context menu: extract IDs from selection
      (or from all cards in the current search if none selected).
    - Button next to the "Sidebar filter" field:
      extracts IDs from ALL cards visible in the Browser search.

Button in deck overview was intentionally removed.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

from anki.collection import Collection
from aqt import gui_hooks, mw
from aqt.browser import Browser
from aqt.qt import (
    QAction,
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QToolButton,
    QMenu,
    QLineEdit,
)
from aqt.utils import showInfo, tooltip

# -------------------------
# UWorld tag patterns
# -------------------------
# v12:
#   #AK_Step1_v12::#UWorld::Step::12345
#   #AK_Step2_v12::#UWorld::Step::12345
#   #AK_Step3_v12::#UWorld::Step::12345
#
# v11 (novo formato):
#   #AK_Step1_v11::#UWorld::10000-99999::14000-14999::14993
#   #AK_Step2_v11::#UWorld::...::...::12345
#   #AK_Step3_v11::#UWorld::...::...::12345
#
# → queremos sempre o ID da **última subtag** (apenas dígitos),
#   ignorando qualquer quantidade de subtags intermediárias.

STEP_PATTERNS = {
    "step1": [
        # V12 (fixo)
        re.compile(r"#AK_Step1_v12::#UWorld::Step::(\d+)"),
        # V11: prefixo fixo + qualquer número de '::algo::' intermediário + '::<ID>'
        re.compile(r"#AK_Step1_v11::#UWorld::(?:[^:\s]+::)*(\d+)"),
    ],
    "step2": [
        re.compile(r"#AK_Step2_v12::#UWorld::Step::(\d+)"),
        re.compile(r"#AK_Step2_v11::#UWorld::(?:[^:\s]+::)*(\d+)"),
    ],
    "step3": [
        # V12: mesmo formato do V11, apenas mudando v11 → v12
        re.compile(r"#AK_Step3_v12::#UWorld::(?:[^:\s]+::)*(\d+)"),
        re.compile(r"#AK_Step3_v11::#UWorld::(?:[^:\s]+::)*(\d+)"),
    ],
}


# -------------------------
# Dialog
# -------------------------

class UWorldExtractorDialog(QDialog):
    def __init__(
        self,
        parent,
        source_label: str,
        step1_ids: Sequence[str],
        step2_ids: Sequence[str],
        step3_ids: Sequence[str],
    ) -> None:
        super().__init__(parent)
        self.step1_ids = list(step1_ids)
        self.step2_ids = list(step2_ids)
        self.step3_ids = list(step3_ids)
        self._setup_ui(source_label)

    def _setup_ui(self, source_label: str) -> None:
        self.setWindowTitle("UWorld Question ID Extractor")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)

        layout = QVBoxLayout()

        src_label = QLabel(f"<b>Source:</b> {source_label}")
        src_label.setStyleSheet("font-size: 14px; padding: 10px;")
        layout.addWidget(src_label)

        layout.addWidget(self._group("Step 1", self.step1_ids))
        layout.addWidget(self._group("Step 2", self.step2_ids))
        layout.addWidget(self._group("Step 3", self.step3_ids))

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def _group(self, step_name: str, ids: Sequence[str]) -> QGroupBox:
        group = QGroupBox(step_name)
        lay = QVBoxLayout()

        lay.addWidget(QLabel(f"<b>Number of questions:</b> {len(ids)}"))

        if ids:
            copy_btn = QPushButton(f"Copy {step_name} IDs")
            copy_btn.clicked.connect(lambda _=False, i=ids, s=step_name: self._copy(i, s))
            copy_btn.setStyleSheet("padding:8px;background:#4CAF50;color:white;font-weight:bold;")
            lay.addWidget(copy_btn)

            preview = ", ".join(ids[:10])
            if len(ids) > 10:
                preview += f"... (+{len(ids)-10} more)"

            p = QLabel(f"<i>Preview:</i> {preview}")
            p.setWordWrap(True)
            p.setStyleSheet("color:#666;padding:5px;")
            lay.addWidget(p)

        else:
            no = QLabel("<i>No questions found</i>")
            no.setStyleSheet("color:#999;padding:5px;")
            lay.addWidget(no)

        group.setLayout(lay)
        return group

    def _copy(self, ids: Sequence[str], step_name: str):
        mw.app.clipboard().setText(",".join(ids))
        tooltip(f"{len(ids)} {step_name} IDs copied to clipboard!")


# -------------------------
# Extraction logic
# -------------------------

def extract_ids(col: Collection, card_ids: Iterable[int]):
    s1, s2, s3 = set(), set(), set()

    for cid in card_ids:
        card = col.get_card(cid)
        tags = " ".join(card.note().tags)

        for pat in STEP_PATTERNS["step1"]:
            for m in pat.finditer(tags):
                s1.add(m.group(1))

        for pat in STEP_PATTERNS["step2"]:
            for m in pat.finditer(tags):
                s2.add(m.group(1))

        for pat in STEP_PATTERNS["step3"]:
            for m in pat.finditer(tags):
                s3.add(m.group(1))

    return sorted(s1, key=int), sorted(s2, key=int), sorted(s3, key=int)


def run(ids, source, parent=None):
    if not ids:
        showInfo("No cards found to extract UWorld IDs from.")
        return

    col = mw.col
    step1, step2, step3 = extract_ids(col, ids)
    dlg = UWorldExtractorDialog(parent or mw, source, step1, step2, step3)
    dlg.exec()


# -------------------------
# Sources
# -------------------------

def extract_current_deck():
    col = mw.col
    deck = col.decks.current()
    name = col.decks.name(deck["id"])
    ids = col.find_cards(f'deck:"{name}"')
    run(ids, f"Current deck: {name}", mw)


def browser_selection(browser: Browser):
    col = mw.col
    sel = []

    # compatibility with different Anki versions
    if hasattr(browser, "selected_cards"):
        sel = list(browser.selected_cards())
    elif hasattr(browser, "selectedCards"):
        sel = list(browser.selectedCards())

    if sel:
        run(sel, f"Browser: {len(sel)} selected cards", browser)
        return

    try:
        search = browser.form.searchEdit.lineEdit().text()
    except Exception:
        search = ""

    ids = col.find_cards(search)
    run(ids, f"Browser: all cards in current search ({len(ids)})", browser)


def browser_visible(browser: Browser):
    col = mw.col
    try:
        search = browser.form.searchEdit.lineEdit().text()
    except Exception:
        search = ""

    ids = col.find_cards(search)
    run(ids, f"Browser (Sidebar): visible cards ({len(ids)})", browser)


# -------------------------
# Browser UI
# -------------------------

def add_tools_menu():
    act = QAction("📋 Extract UWorld IDs (current deck)", mw)
    act.triggered.connect(extract_current_deck)
    mw.form.menuTools.addAction(act)


def browser_menu(browser: Browser):
    act = QAction("Extract UWorld IDs (selection/search)", browser)
    act.triggered.connect(lambda _, b=browser: browser_selection(b))
    browser.form.menuEdit.addAction(act)


def browser_context(browser: Browser, menu: QMenu):
    act = QAction("Extract UWorld IDs (selection/search)", browser)
    act.triggered.connect(lambda _, b=browser: browser_selection(b))
    menu.addSeparator()
    menu.addAction(act)


def find_sidebar_filter(browser: Browser):
    for w in browser.findChildren(QLineEdit):
        try:
            if w.placeholderText().lower().strip() == "sidebar filter":
                return w
        except:
            pass
    return None


def add_sidebar_button(browser: Browser):
    if getattr(browser, "_uworld_sidebar_button_added", False):
        return

    edit = find_sidebar_filter(browser)
    if not edit:
        return

    parent = edit.parentWidget()
    layout = parent.layout()
    if not layout:
        return

    btn = QToolButton(parent)
    btn.setText("Show UWorld Question Ids")
    btn.setToolTip("Extract UWorld IDs from all visible cards in the Browser search")
    btn.clicked.connect(lambda _, b=browser: browser_visible(b))

    layout.addWidget(btn)
    browser._uworld_sidebar_button_added = True


def on_browser_show(browser: Browser):
    add_sidebar_button(browser)


# -------------------------
# Init
# -------------------------

def init_addon():
    add_tools_menu()
    gui_hooks.browser_menus_did_init.append(browser_menu)
    gui_hooks.browser_will_show_context_menu.append(browser_context)
    gui_hooks.browser_will_show.append(on_browser_show)

init_addon()