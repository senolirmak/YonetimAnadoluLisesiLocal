# -*- coding: utf-8 -*-
import re
import warnings

import pandas as pd
from openpyxl import load_workbook

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


def normalize_columns(df):
    """DataFrame kolon isimlerini ascii, kucuk harf, alt cizgili formata cevirir."""
    def clean(col):
        col = str(col).strip().lower()
        tr = str.maketrans("şçöğüı ", "scogui_")
        col = col.translate(tr)
        col = re.sub(r"[^a-z0-9_]", "", col)
        return col
    df.columns = [clean(c) for c in df.columns]
    return df


def normalize_sube_cell(s):
    """'9/A, 9/B' gibi alanlari listeye cevirir."""
    if pd.isna(s):
        return []
    s = str(s).upper().replace(" ", "")
    return [x for x in s.split(",") if x]


def safe_sheet_name(name):
    """Excel sheet name icin guvenli isim uretir (max 31 karakter)."""
    name = name.replace("/", "_").replace("\\", "_").replace("?", "_").replace("*", "_")
    name = name.replace("[", "(").replace("]", ")")
    return name[:31]


def iter_rows(file_path):
    """Hem .xls hem .xlsx dosyalarini satirlar halinde dondurur."""
    ext = str(file_path).lower()
    if ext.endswith(".xls"):
        import xlrd
        wb = xlrd.open_workbook(file_path)
        ws = wb.sheet_by_index(0)
        for i in range(ws.nrows):
            yield ws.row_values(i)
    else:
        wb = load_workbook(file_path)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            yield row
