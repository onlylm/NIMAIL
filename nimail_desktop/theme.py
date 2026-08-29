STYLE = r"""
QWidget {
  color: #17243a;
  font-family: "Microsoft YaHei UI", "Segoe UI";
  font-size: 13px;
}
QMainWindow, #root { background: #f4f7fb; }
#sidebar { background: #102447; border: none; }
#sidebar QLabel { color: #ffffff; }
#brandName { font-size: 16px; font-weight: 750; }
#brandSub { color: #aebed7; font-size: 10px; }
#userName { color: #ffffff; font-size: 14px; font-weight: 650; }
#userRole { color: #9fb1cc; font-size: 10px; }
#userAvatar { min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; border-radius: 14px; background: #eaf1ff; color: #102447; font-size: 10px; }
QPushButton#navButton {
  min-height: 40px;
  color: #cbd7e8;
  text-align: left;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 650;
}
QPushButton#navButton:hover { background: #173867; color: white; }
QPushButton#navButton:checked { background: #2762e9; color: white; }
QPushButton#navButton[collapsed="true"] { text-align: center; padding: 0; }
#content { background: #f4f7fb; }
#appBody { background: #f4f7fb; }
#topbar { background: #ffffff; border-bottom: 1px solid #dce4ee; }
#topbarTitle { color: #17243a; font-size: 14px; font-weight: 750; }
#topbarSub { color: #8491a5; font-size: 10px; }
#topStatus { color: #9a6a19; font-size: 11px; font-weight: 650; }
#topStatus[ok="true"] { color: #15815f; }
#pageScroll, #pageScroll > QWidget > QWidget { background: #f4f7fb; border: 0; }
#pageTitle { font-size: 22px; font-weight: 800; color: #10213a; }
#pageSub { color: #8491a5; font-size: 12px; }
#sectionTitle { font-size: 16px; font-weight: 800; color: #17243a; }
#card {
  background: #ffffff;
  border: 1px solid #dce4ee;
  border-radius: 10px;
}
#statValue { font-size: 30px; font-weight: 850; color: #2762e9; }
#statLabel { color: #6c7b90; }
#statusChip {
  background: #ffffff;
  border: 1px solid #dce4ee;
  border-radius: 10px;
  padding: 9px 13px;
  color: #26364e;
  font-size: 13px;
  font-weight: 650;
}
#statusChip[ok="true"] { color: #176e56; border-color: #ccebdd; background: #f6fffb; }
#fieldLabel { color: #26364e; font-size: 13px; font-weight: 700; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
  min-height: 36px;
  background: #ffffff;
  border: 1px solid #d4deea;
  border-radius: 7px;
  padding: 7px 11px;
  selection-background-color: #2762e9;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
  border: 1px solid #2762e9;
}
QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button { border: 0; width: 24px; }
QPushButton#primary {
  min-height: 38px;
  background: #2762e9;
  color: white;
  border: 0;
  border-radius: 7px;
  padding: 8px 20px;
  font-weight: 750;
}
QPushButton#primary:hover { background: #174fc7; }
QPushButton#primary:disabled { background: #96addb; }
QPushButton#secondary {
  min-height: 36px;
  background: white;
  color: #25415f;
  border: 1px solid #d4deea;
  border-radius: 7px;
  padding: 7px 15px;
  font-weight: 650;
}
QPushButton#secondary:hover { background: #f3f7fb; border-color: #bfcddd; }
QPushButton#danger {
  min-height: 36px;
  background: #fff2f1;
  color: #b52c22;
  border: 1px solid #f0c8c5;
  border-radius: 7px;
  padding: 7px 15px;
  font-weight: 700;
}
QCheckBox { spacing: 7px; color: #46566d; }
QTableWidget {
  background: #ffffff;
  border: 1px solid #dce4ee;
  border-radius: 11px;
  gridline-color: #e6ebf2;
  alternate-background-color: #fbfcfe;
  selection-background-color: #e8efff;
  selection-color: #17243a;
}
QHeaderView::section {
  min-height: 42px;
  background: #f7f9fc;
  color: #34435a;
  border: 0;
  border-bottom: 1px solid #dce4ee;
  padding: 7px 12px;
  font-weight: 750;
}
QTableWidget::item { padding: 7px 12px; border-bottom: 1px solid #edf1f5; }
QTableWidget::item:selected { background: #e8efff; color: #17243a; }
QProgressBar {
  min-height: 9px;
  max-height: 9px;
  border: 0;
  border-radius: 4px;
  background: #e0e6ed;
}
QProgressBar::chunk { border-radius: 4px; background: #2e76ea; }
#progressFraction { color: #2762e9; font-size: 18px; font-weight: 800; }
#progressPercent { color: #65738a; font-size: 15px; font-weight: 700; }
#batchError { background: #fff2f1; border: 1px solid #f0c8c5; border-radius: 9px; padding: 9px 12px; color: #b52c22; }
#notice { background: #fff8ea; border: 1px solid #edd6a7; border-radius: 10px; padding: 11px; color: #84520f; }
#privacy { background: #edf3ff; border: 1px solid #cbdafa; border-radius: 12px; color: #315686; }
#manualCookie { background: #f9fbfd; }
#cookieSuccess { color: #15815f; font-weight: 700; }
#selectionCount { color: #6c7b90; font-size: 13px; font-weight: 650; }
QMenu {
  background: #ffffff;
  border: 1px solid #d4deea;
  border-radius: 9px;
  padding: 6px;
}
QMenu::item { min-width: 180px; padding: 9px 24px 9px 12px; border-radius: 6px; }
QMenu::item:selected { background: #e8efff; color: #174fc7; }
QMenu::item:disabled { color: #a1acbb; }
QMenu::separator { height: 1px; background: #e6ebf2; margin: 5px 8px; }
QToolTip { background: #17243a; color: white; border: 0; }
"""


DARK_STYLE = r"""
QWidget { color: #e7edf8; }
QMainWindow, #root, #content, #appBody, #pageScroll, #pageScroll > QWidget > QWidget { background: #101620; }
#topbar { background: #171e2a; border-bottom-color: #2c3645; }
#topbarTitle, #pageTitle, #sectionTitle { color: #e7edf8; }
#topbarSub, #pageSub, #statLabel, #selectionCount { color: #98a6ba; }
#card { background: #171e2a; border-color: #2d3746; }
#statusChip { background: #171e2a; border-color: #3b4658; color: #dbe4f2; }
#statusChip[ok="true"] { color: #72d8b7; border-color: #275a4c; background: #15241f; }
#fieldLabel { color: #c9d3e2; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
  color: #e7edf8; background: #111822; border-color: #3b4658;
}
QLineEdit:read-only { color: #9dbcf1; background: #151c26; }
QPushButton#secondary { color: #dce5f2; background: #171e2a; border-color: #3b4658; }
QPushButton#secondary:hover { background: #202a38; border-color: #526178; }
QPushButton#danger { color: #ff9c91; background: #291b1b; border-color: #70433e; }
QCheckBox { color: #c4cede; }
QTableWidget { color: #e7edf8; background: #171e2a; border-color: #2d3746; alternate-background-color: #151c26; selection-background-color: #243755; selection-color: #f3f7ff; }
QHeaderView::section { color: #b7c3d4; background: #151c26; border-bottom-color: #303a48; }
QTableWidget::item { border-bottom-color: #2c3543; }
QTableWidget::item:selected { background: #243755; color: #f3f7ff; }
QMenu { color: #e7edf8; background: #1b2330; border-color: #3b4658; }
QMenu::item:selected { background: #243755; color: #b9d2ff; }
QMenu::separator { background: #354153; }
QProgressBar { background: #2c3543; }
#notice { color: #f0c47d; background: #2b2418; border-color: #5f4a28; }
#privacy { color: #b8cff3; background: #18243a; border-color: #33496a; }
#manualCookie { background: #111822; }
#batchError { color: #ff9c91; background: #291b1b; border-color: #70433e; }
QScrollBar:vertical { background: #101620; }
"""
