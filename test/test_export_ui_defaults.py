from PyQt5 import QtWidgets


def test_export_tab_defaults_merge_roads_enabled():
    from window import Ui_MainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    main_window = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(main_window)

    assert ui.merge_roads_checkbox.isChecked() is True
    assert ui.export_buildings_checkbox.isChecked() is True
