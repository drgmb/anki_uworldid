# -*- coding: utf-8 -*-
"""
UWorld Question ID Extractor (Cross-platform Enhanced)
Extracts UWorld question IDs from Anki card tags.

Features:
- Tools menu: extract IDs from current deck.
- Browser:
    - Edit menu + context menu: extract IDs from selection
      (or from all cards in the current search if none selected).
    - Button next to the "Sidebar filter" field:
      extracts IDs from ALL cards visible in the Browser search.

Extra (custom):
- Persistent list of "answered" UWorld IDs stored in a JSON file.
- Option to filter out already-answered IDs from results (default: ON).
- Tools menu dialog to:
    - toggle filter on/off
    - add answered IDs
    - view saved answered IDs
    - clear all answered IDs
- Button in result dialog to:
    - mark all displayed IDs as answered
- Button on Anki home screen (top-right):
    - opens the "answered IDs" dialog directly
- UI mostra quantos IDs foram ocultados por já estarem respondidos.
"""

from __future__ import annotations

import re
import os
import json
import shutil
from datetime import datetime
from typing import Iterable, List, Sequence, Optional, Dict




from anki.collection import Collection
from aqt import gui_hooks, mw
from aqt.browser import Browser
from aqt.qt import (
    QAction,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QToolButton,
    QMenu,
    QLineEdit,
    QTimer,
    QCheckBox,
)
from aqt.utils import showInfo, tooltip, askUser

# =========================================================
# Config helpers (arquivo JSON próprio na pasta do add-on)
# =========================================================

def _addon_id() -> str:
    """Resolve o ID real do add-on em runtime (independente da pasta)."""
    try:
        return mw.addonManager.addonFromModule(__name__) or __name__
    except Exception:
        return __name__


ADDON_ID = _addon_id()

# Nome do arquivo JSON que vai guardar os dados
CONFIG_FILENAME = "uworld_ids_config.json"
BACKUP_DIRNAME = "uworld_ids_backups"


# Nome do arquivo JSON que vai guardar os dados
CONFIG_FILENAME = "uworld_ids_config.json"
# Pasta onde serão guardados os backups do JSON
BACKUP_DIRNAME = "uworld_ids_backups"



def _config_path() -> str:
    """Retorna o caminho completo do arquivo de config dentro da pasta do add-on."""
    try:
        folder = mw.addonManager.addonFolder(ADDON_ID)
    except Exception:
        # fallback: mesma pasta do arquivo atual
        folder = os.path.dirname(__file__)
    return os.path.join(folder, CONFIG_FILENAME)

def _backup_config_file_if_exists() -> None:
    """
    Se o arquivo de config atual existir, faz uma cópia dele
    para a pasta de backups, com timestamp no nome.
    Mantém no máximo 10 backups, apagando os mais antigos.
    """
    try:
        cfg_path = _config_path()
        if not os.path.exists(cfg_path):
            return  # nada para backupar

        # pasta do add-on
        try:
            folder = mw.addonManager.addonFolder(ADDON_ID)
        except Exception:
            folder = os.path.dirname(__file__)

        backup_dir = os.path.join(folder, BACKUP_DIRNAME)
        os.makedirs(backup_dir, exist_ok=True)

        # cria backup novo
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        backup_name = f"uworld_ids_config_{ts}.json"
        backup_path = os.path.join(backup_dir, backup_name)

        shutil.copy2(cfg_path, backup_path)
        print(f"[UWorld IDs] Backup de config criado em: {backup_path}")

        # ---------- rotação: manter no máximo 10 ----------
        # lista todos os backups que seguem o padrão
        all_backups = []
        for fname in os.listdir(backup_dir):
            if fname.startswith("uworld_ids_config_") and fname.endswith(".json"):
                all_backups.append(fname)

        if len(all_backups) > 10:
            # como o nome começa com YYYY-MM-DD..., ordenar por nome já é cronológico
            all_backups.sort()
            # quantos precisam ser removidos
            excess = len(all_backups) - 10
            to_remove = all_backups[:excess]
            for fname in to_remove:
                try:
                    os.remove(os.path.join(backup_dir, fname))
                    print(f"[UWorld IDs] Backup antigo removido: {fname}")
                except Exception as e:
                    print(f"[UWorld IDs] Erro ao remover backup antigo {fname}: {e}")

    except Exception as e:
        # backup não é crítico, então só loga erro
        print(f"[UWorld IDs] Erro ao criar backup de config: {e}")




def _normalize_ids_list(raw) -> List[str]:
    """Normaliza lista de IDs: tudo string numérica, única, ordenada."""
    if not raw:
        return []

    ids: List[str] = []

    # Se for set, converte para lista
    if isinstance(raw, set):
        raw = list(raw)

    for item in raw:
        s = str(item).strip()
        if s.isdigit():
            ids.append(s)

    unique_ids = list(set(ids))
    return sorted(unique_ids, key=int)


def _load_raw_config() -> dict:
    """Lê o JSON cru do disco (ou retorna {} se não existir)."""
    path = _config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[UWorld IDs] Erro ao ler config: {e}")
        return {}
    


def _save_raw_config(cfg: dict) -> None:
    """Grava o JSON cru no disco, com backup da versão anterior."""
    path = _config_path()
    try:
        # antes de sobrescrever, guarda uma cópia da versão atual (se existir)
        _backup_config_file_if_exists()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[UWorld IDs] Erro ao salvar config: {e}")



def get_config() -> dict:
    """Obtém configuração normalizada."""
    cfg = _load_raw_config() or {}

    if "answered_ids" not in cfg:
        cfg["answered_ids"] = []
    if "filter_used" not in cfg:
        cfg["filter_used"] = True

    cfg["answered_ids"] = _normalize_ids_list(cfg.get("answered_ids", []))
    cfg["filter_used"] = bool(cfg.get("filter_used", True))

    return cfg


def save_config(cfg: dict) -> None:
    """Salva configuração normalizada."""
    cfg["answered_ids"] = _normalize_ids_list(cfg.get("answered_ids", []))
    cfg["filter_used"] = bool(cfg.get("filter_used", True))
    _save_raw_config(cfg)


def get_answered_ids() -> List[str]:
    """Lista de IDs já respondidos (strings numéricas)."""
    cfg = get_config()
    return _normalize_ids_list(cfg.get("answered_ids", []))


def set_answered_ids(ids: Iterable[str]) -> None:
    """Define lista de IDs já respondidos."""
    cfg = get_config()
    cfg["answered_ids"] = _normalize_ids_list(ids)
    save_config(cfg)


def get_filter_used() -> bool:
    """Se True, filtra IDs já respondidos na extração."""
    cfg = get_config()
    return bool(cfg.get("filter_used", True))


def set_filter_used(flag: bool) -> None:
    """Define se deve filtrar IDs já respondidos."""
    cfg = get_config()
    cfg["filter_used"] = bool(flag)
    save_config(cfg)


# =========================================================
# Padrões de tags UWorld
# =========================================================

STEP_PATTERNS = {
    "step1": [
        re.compile(r"#AK_Step1_v12::#UWorld::Step::(\d+)"),
        re.compile(r"#AK_Step1_v11::#UWorld::(?:[^:\s]+::)*(\d+)"),
    ],
    "step2": [
        re.compile(r"#AK_Step2_v12::#UWorld::Step::(\d+)"),
        re.compile(r"#AK_Step2_v11::#UWorld::(?:[^:\s]+::)*(\d+)"),
    ],
    "step3": [
        re.compile(r"#AK_Step3_v12::#UWorld::(?:[^:\s]+::)*(\d+)"),
        re.compile(r"#AK_Step3_v11::#UWorld::(?:[^:\s]+::)*(\d+)"),
    ],
}


# =========================================================
# Dialog principal (resultado)
# =========================================================

class UWorldExtractorDialog(QDialog):
    """Dialog que mostra os IDs extraídos."""

    def __init__(
        self,
        parent,
        source_label: str,
        step1_ids: Sequence[str],
        step2_ids: Sequence[str],
        step3_ids: Sequence[str],
        filtered_counts: Optional[Dict[str, int]] = None,
    ) -> None:
        super().__init__(parent)
        self.step1_ids = list(step1_ids)
        self.step2_ids = list(step2_ids)
        self.step3_ids = list(step3_ids)
        # filtered_counts = {"step1": X, "step2": Y, "step3": Z}
        self.filtered_counts: Dict[str, int] = filtered_counts or {}
        self._setup_ui(source_label)

    def _setup_ui(self, source_label: str) -> None:
        self.setWindowTitle("UWorld Question ID Extractor")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)

        layout = QVBoxLayout()

        src_label = QLabel(f"<b>Source:</b> {source_label}")
        src_label.setStyleSheet("font-size: 14px; padding: 10px;")
        layout.addWidget(src_label)

        # Resumo de quantos IDs foram filtrados (se o filtro estiver ativo)
        total_filtered = sum(self.filtered_counts.values()) if self.filtered_counts else 0
        if get_filter_used() and total_filtered > 0:
            info = QLabel(
                f"<b>{total_filtered} ID(s) já respondido(s) foram ocultados pelo filtro.</b>"
            )
            info.setStyleSheet("color:#e67e22; padding: 5px 10px;")
            layout.addWidget(info)

        layout.addWidget(self._group("Step 1", self.step1_ids))
        layout.addWidget(self._group("Step 2", self.step2_ids))
        layout.addWidget(self._group("Step 3", self.step3_ids))

        # Só o botão de fechar agora
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def _group(self, step_name: str, ids: Sequence[str]) -> QGroupBox:
        group = QGroupBox(step_name)
        lay = QVBoxLayout()

        # Mapeia "Step 1" -> "step1", etc.
        key = step_name.lower().replace(" ", "")
        filtered_here = self.filtered_counts.get(key, 0)

        label_text = f"<b>Number of questions:</b> {len(ids)}"
        if get_filter_used() and filtered_here > 0:
            label_text += f"  (filtrados: {filtered_here} já respondidos)"

        count_label = QLabel(label_text)
        lay.addWidget(count_label)

        if ids:
            copy_btn = QPushButton(f"Copy {step_name} IDs")
            copy_btn.clicked.connect(lambda _=False, i=ids, s=step_name: self._copy(i, s))
            copy_btn.setStyleSheet(
                "padding:8px;background:#4CAF50;color:white;font-weight:bold;"
            )
            lay.addWidget(copy_btn)

            preview = ", ".join(ids[:10])
            if len(ids) > 10:
                preview += f"... (+{len(ids) - 10} more)"

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
        if mw and mw.app:
            mw.app.clipboard().setText(",".join(ids))
            tooltip(f"{len(ids)} {step_name} IDs copied to clipboard!")



# =========================================================
# Dialog de configuração de IDs respondidos
# =========================================================

class AnsweredIdsDialog(QDialog):
    """
    Tela acessada pelo menu Tools ou botão da home:

    - Checkbox: filtrar ou não IDs já respondidos.
    - Campo de texto para adicionar novos IDs (separados por vírgula).
    - Botão para ver todos os IDs salvos.
    """

    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("UWorld - IDs já respondidos")
        self.resize(520, 240)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Checkbox: usar filtro ou não
        self.chk_filter = QCheckBox("Filter IDs already answered in the extraction (recommended)")
        self.chk_filter.setChecked(get_filter_used())
        layout.addWidget(self.chk_filter)

        # Informação sobre total de IDs salvos
        total_ids = len(get_answered_ids())
        self.lbl_count = QLabel(f"<b>Total IDs saved:</b> {total_ids}")
        self.lbl_count.setStyleSheet("padding: 5px; color: #2196F3;")
        layout.addWidget(self.lbl_count)

        # Campo para adicionar IDs
        layout.addWidget(QLabel("Add IDs already answered (numbers, separated by commas):"))
        self.txt_ids = QLineEdit()
        self.txt_ids.setPlaceholderText("Ex.: 12345, 67890, 111213")
        layout.addWidget(self.txt_ids)

        # Linha de botões (Adicionar + Ver IDs)
        btn_layout = QHBoxLayout()

        self.btn_add = QPushButton("Adicionar")
        self.btn_add.clicked.connect(self.on_add_ids)
        self.btn_add.setStyleSheet("background:#4CAF50;color:white;padding:8px;")
        btn_layout.addWidget(self.btn_add)

        self.btn_show = QPushButton("Ver IDs")
        self.btn_show.clicked.connect(self.on_show_ids)
        btn_layout.addWidget(self.btn_show)

        layout.addLayout(btn_layout)

        # Botão fechar
        self.btn_close = QPushButton("Fechar e Salvar")
        self.btn_close.clicked.connect(self.on_close)
        self.btn_close.setStyleSheet("padding:8px;font-weight:bold;")
        layout.addWidget(self.btn_close)

    def _update_count_label(self):
        """Atualiza o label com o total de IDs."""
        total = len(get_answered_ids())
        self.lbl_count.setText(f"<b>Total de IDs salvos:</b> {total}")

    def on_add_ids(self):
        """Adiciona novos IDs à lista."""
        text = self.txt_ids.text().strip()
        if not text:
            tooltip("No ID provided.")
            return

        parts = [p.strip() for p in text.split(",") if p.strip()]
        new_ids: List[str] = []
        invalid: List[str] = []

        for p in parts:
            if p.isdigit():
                new_ids.append(p)
            else:
                invalid.append(p)

        if invalid:
            showInfo(
                "The following values are not valid numeric IDs and have been ignored:\n"
                + ", ".join(invalid)
            )

        if new_ids:
            existing_ids = get_answered_ids()
            all_ids = existing_ids + new_ids
            set_answered_ids(all_ids)

            self._update_count_label()
            self.txt_ids.clear()

            final_count = len(get_answered_ids())
            added_count = final_count - len(existing_ids)
            tooltip(f"{added_count} ID(s) added. Total: {final_count}")

    def on_show_ids(self):
        """Mostra todos os IDs salvos."""
        current_ids = get_answered_ids()
        if not current_ids:
            showInfo("No ID saved yet.")
            return

        ids_str = ", ".join(current_ids)
        showInfo(f"Saved IDs ({len(current_ids)} total):\n\n{ids_str}")

    def on_close(self):
        """Salva configurações e fecha."""
        set_filter_used(self.chk_filter.isChecked())
        tooltip("Settings saved!")
        self.accept()

# =========================================================
# Fim da Class AnseredIdsDialog
# =========================================================
def open_answered_ids_dialog():
    """Abre o dialog de gerenciamento de IDs respondidos."""
    dlg = AnsweredIdsDialog(mw)
    dlg.exec()


# =========================================================
# Lógica de extração
# =========================================================

def extract_ids(col: Collection, card_ids: Iterable[int]):
    """Extrai IDs UWorld dos cards e informa quantos foram filtrados."""
    s1, s2, s3 = set(), set(), set()

    for cid in card_ids:
        try:
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
        except Exception as e:
            print(f"[UWorld IDs] Error processing card {cid}: {e}")
            continue

    # listas "brutas" (sem filtro)
    raw_s1 = sorted(s1, key=int)
    raw_s2 = sorted(s2, key=int)
    raw_s3 = sorted(s3, key=int)

    filtered_counts = {"step1": 0, "step2": 0, "step3": 0}

    if get_filter_used():
        answered = set(get_answered_ids())

        step1 = [x for x in raw_s1 if x not in answered]
        step2 = [x for x in raw_s2 if x not in answered]
        step3 = [x for x in raw_s3 if x not in answered]

        filtered_counts["step1"] = len(raw_s1) - len(step1)
        filtered_counts["step2"] = len(raw_s2) - len(step2)
        filtered_counts["step3"] = len(raw_s3) - len(step3)
    else:
        # Sem filtro: tudo passa, e nada "filtrado"
        step1 = raw_s1
        step2 = raw_s2
        step3 = raw_s3

    return step1, step2, step3, filtered_counts


def run(ids, source, parent=None):
    """Executa a extração e mostra o dialog de resultados."""
    if not ids:
        showInfo("No cards found to extract UWorld IDs from.")
        return

    if not mw or not mw.col:
        showInfo("Collection not loaded.")
        return

    col = mw.col
    step1, step2, step3, filtered_counts = extract_ids(col, ids)
    dlg = UWorldExtractorDialog(parent or mw, source, step1, step2, step3, filtered_counts)
    dlg.exec()


# =========================================================
# Helpers de Browser
# =========================================================

def get_search_text(browser: Browser) -> str:
    """Obtém texto de busca de forma compatível entre versões."""
    try:
        se = browser.form.searchEdit
        # Anki 2.1.x / 2.1.24+ / 23 / 25 (Qt5/Qt6)
        if hasattr(se, "lineEdit"):
            return se.lineEdit().text()
        # Algumas versões / forks expõem .text() direto
        if hasattr(se, "text"):
            return se.text()
    except (AttributeError, RuntimeError) as e:
        print(f"[UWorld IDs] Error getting search text from searchEdit: {e}")

    # fallback extra
    try:
        if hasattr(browser, "search_box"):
            return browser.search_box.text()
    except (AttributeError, RuntimeError) as e:
        print(f"[UWorld IDs] Error getting search text from search_box: {e}")

    return ""


def get_selected_cards(browser: Browser) -> List[int]:
    """Obtém cards selecionados de forma compatível entre versões."""
    try:
        if hasattr(browser, "selected_cards"):
            return list(browser.selected_cards())
        elif hasattr(browser, "selectedCards"):
            return list(browser.selectedCards())
        elif hasattr(browser, "table") and hasattr(browser.table, "get_selected_card_ids"):
            return list(browser.table.get_selected_card_ids())
    except (AttributeError, RuntimeError) as e:
        print(f"[UWorld IDs] Error getting selected cards: {e}")
    return []


# =========================================================
# Fontes de extração
# =========================================================

def extract_current_deck():
    """Extrai IDs do deck atual."""
    if not mw or not mw.col:
        showInfo("Collection not loaded.")
        return

    col = mw.col
    try:
        deck = col.decks.current()
        name = col.decks.name(deck["id"])
        ids = col.find_cards(f'deck:"{name}"')
        run(ids, f"Current deck: {name}", mw)
    except Exception as e:
        showInfo(f"Error extracting from current deck: {str(e)}")


def browser_selection(browser: Browser):
    """Extrai IDs da seleção ou busca atual do browser."""
    if not mw or not mw.col:
        showInfo("Collection not loaded.")
        return

    col = mw.col
    sel = get_selected_cards(browser)

    if sel:
        run(sel, f"Browser: {len(sel)} selected cards", browser)
        return

    search = get_search_text(browser)
    try:
        ids = col.find_cards(search)
        run(ids, f"Browser: all cards in current search ({len(ids)})", browser)
    except Exception as e:
        showInfo(f"Error in browser selection: {str(e)}")


def browser_visible(browser: Browser):
    """Extrai IDs de todos os cards visíveis no browser."""
    if not mw or not mw.col:
        showInfo("Collection not loaded.")
        return

    col = mw.col
    search = get_search_text(browser)

    try:
        ids = col.find_cards(search)
        run(ids, f"Browser (Sidebar): visible cards ({len(ids)})", browser)
    except Exception as e:
        showInfo(f"Error extracting visible cards: {str(e)}")


# =========================================================
# UI do Browser / Tools
# =========================================================

def add_tools_menu():
    """Adiciona itens ao menu Tools."""
    act_extract = QAction("📋 Extract UWorld IDs (current deck)", mw)
    act_extract.triggered.connect(extract_current_deck)
    mw.form.menuTools.addAction(act_extract)

    act_cfg = QAction("⚙️ UWorld answered IDs (filter & store)", mw)
    act_cfg.triggered.connect(open_answered_ids_dialog)
    mw.form.menuTools.addAction(act_cfg)


def browser_menu(browser: Browser):
    """Adiciona item ao menu Edit do browser."""
    act = QAction("Extract UWorld IDs (selection/search)", browser)
    act.triggered.connect(lambda _, b=browser: browser_selection(b))
    browser.form.menuEdit.addAction(act)


def browser_context(browser: Browser, menu: QMenu):
    """Adiciona item ao menu de contexto do browser."""
    act = QAction("Extract UWorld IDs (selection/search)", browser)
    act.triggered.connect(lambda _, b=browser: browser_selection(b))
    menu.addSeparator()
    menu.addAction(act)


def find_sidebar_filter(browser: Browser) -> Optional[QLineEdit]:
    """Encontra o campo Sidebar Filter de forma robusta."""
    for w in browser.findChildren(QLineEdit):
        try:
            placeholder = w.placeholderText()
            if placeholder and placeholder.lower().strip() == "sidebar filter":
                return w
        except (AttributeError, RuntimeError):
            continue
    return None


def add_sidebar_button(browser: Browser):
    """Adiciona botão próximo ao Sidebar Filter."""
    if getattr(browser, "_uworld_sidebar_button_added", False):
        return

    edit = find_sidebar_filter(browser)
    if not edit:
        QTimer.singleShot(200, lambda: add_sidebar_button(browser))
        return

    parent = edit.parentWidget()
    if not parent:
        return

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
    """Hook quando browser é exibido."""
    QTimer.singleShot(100, lambda: add_sidebar_button(browser))


# =========================================================
# Botão na tela inicial (top toolbar, canto superior direito)
# =========================================================

def on_top_toolbar_redraw(toolbar):
    """
    Adiciona um botão na área superior direita da home do Anki
    para abrir o gerenciador de IDs respondidos.
    """

    def _handler(*args, **kwargs) -> None:
        # Ignora quaisquer argumentos que o Anki passar e só abre o diálogo
        open_answered_ids_dialog()

    toolbar.link_handlers["uworld_ids_add"] = _handler

    js = r"""
    (function() {
        var btnId = 'uworld-ids-add-btn';
        if (document.getElementById(btnId)) {
            return;
        }

        var topRight = document.querySelector('.top-right') || 
                       document.querySelector('.topbuts') ||
                       document.querySelector('.tdright');
        
        if (!topRight) {
            var allDivs = document.querySelectorAll('div');
            for (var i = 0; i < allDivs.length; i++) {
                var d = allDivs[i];
                if (d.style.float === 'right' || 
                    d.align === 'right' ||
                    (d.className && d.className.indexOf('right') !== -1)) {
                    topRight = d;
                    break;
                }
            }
        }

        if (!topRight) {
            console.log('UWorld IDs: Could not find top-right container');
            return;
        }

        var btn = document.createElement('button');
        btn.id = btnId;
        btn.textContent = 'Add UW IDs';
        btn.title = 'Adicionar IDs UWorld já respondidos';
        btn.style.cssText = `
            background: transparent;
            border: 1px solid rgba(255,255,255,0.3);
            color: var(--fg);
            padding: 4px 8px;
            margin: 0 4px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            font-weight: bold;
            transition: all 0.2s;
        `;
        
        btn.onmouseover = function() {
            this.style.background = 'rgba(255,255,255,0.1)';
            this.style.borderColor = 'rgba(255,255,255,0.5)';
        };
        
        btn.onmouseout = function() {
            this.style.background = 'transparent';
            this.style.borderColor = 'rgba(255,255,255,0.3)';
        };
        
        btn.onclick = function(e) {
            e.preventDefault();
            pycmd('uworld_ids_add');
            return false;
        };

        topRight.insertBefore(btn, topRight.firstChild);
    })();
    """
    toolbar.web.eval(js)


# =========================================================
# Init
# =========================================================

def init_addon():
    """Inicializa o addon."""
    try:
        add_tools_menu()
        gui_hooks.top_toolbar_did_redraw.append(on_top_toolbar_redraw)
        gui_hooks.browser_menus_did_init.append(browser_menu)
        gui_hooks.browser_will_show_context_menu.append(browser_context)
        gui_hooks.browser_will_show.append(on_browser_show)
        print("[UWorld IDs] Add-on initialized successfully")
        print("[UWorld IDs] Config path:", _config_path())
    except Exception as e:
        print(f"[UWorld IDs] Error initializing addon: {e}")


init_addon()
