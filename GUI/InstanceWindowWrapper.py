from PyQt5.QtWidgets import *
from PyQt5.QtCore import QThread

from functools import partial
from os import path
from webbrowser import open as webopen

from API.MultiMC import MultiMCInstance
from API.CurseAPI import CurseAPI, CurseProject

from Utils.Utils import clear_layout, load_style_sheet, human_format, confirmation
from Utils.Downloader import DownloaderThread
from Utils.Config import Config, Setting

from GUI.InstanceWindow import Ui_InstanceWindow

from GUI.FileDialogWrapper import FileDialog
from GUI.DownloadDialogWrapper import DownloadDialog

from GUI.ModBrowseWidget import Ui_ModBrowseWidget
from GUI.ModWidget import Ui_ModWidget


class InstanceWindow:
    def __init__(self, instance: MultiMCInstance, curse: CurseAPI, conf: Config, icon_dir: str):
        self.curse = curse
        self.icon_dir = icon_dir
        self.instance = instance
        self.installed_mods = list()
        self.conf = conf

        self.mod_widgets = list()

        self.win = QMainWindow()
        self.ui = Ui_InstanceWindow()

        self.ui.setupUi(self.win)

        self.win.setWindowTitle("Editing {}".format(instance.name))

        self.ui.pack_version.setText("Minecraft: {}".format(instance.version))

        if instance.file:
            self.file = self.curse.get_file(instance.file)
            self.pack = self.curse.get_project(self.file.project)
            self.ui.pack_pack.setText("Modpack ID: {} ({})".format(self.pack.name, self.file.pub_time))
        else:
            self.file = None
            self.pack = None
            self.ui.pack_pack.hide()

        self.setup_mods()
        self.icon_threads = []
        self.setup_mod_browse(curse.get_mod_list(self.instance.version))

        self.ui.pack_search.textChanged.connect(self.q_typed)
        self.ui.pack_search.returnPressed.connect(self.search_packs)
        self.ui.pack_search_button.clicked.connect(self.search_packs)

        self.ui.meta_scan.clicked.connect(self.mod_scan)

        self.style = load_style_sheet('main')

        self.win.setStyleSheet(self.style)

        self.win.show()

    def q_typed(self):
        if not self.conf.read(Setting.live_search):
            return
        if self.ui.pack_search.text() == "":
            self.setup_mod_browse(self.curse.get_mod_list(self.instance.version))
            return
        self.setup_mod_browse(self.curse.search(self.ui.pack_search.text(), "mod", self.instance.version))

    def search_packs(self):
        if self.ui.pack_search.text() == "":
            self.setup_mod_browse(self.curse.get_mod_list(self.instance.version))
            return
        self.setup_mod_browse(self.curse.search(self.ui.pack_search.text(), "mod", self.instance.version))

    def setup_mods(self):
        self.installed_mods = [self.curse.get_file(i["id"]).project for i in self.instance.mods]
        clear_layout(self.ui.mod_box)

        rl_mods = [i for i in self.instance.mods if self.curse.get_file(i["id"])]
        rl_mods.sort(key=lambda x: self.curse.get_project(self.curse.get_file(x["id"]).project).name.lower())

        for mod in rl_mods:
            widget = QWidget()
            el = Ui_ModWidget()
            el.setupUi(widget)

            modf = self.curse.get_file(mod["id"])
            if not modf:
                continue
            proj = self.curse.get_project(modf.project)
            el.mod_name.setText(proj.name)

            el.mod_delete.clicked.connect(partial(self.mod_delete, mod["path"]))
            el.mod_update.clicked.connect(partial(self.mod_install, proj, True))

            el.mod_install.hide()
            el.mod_info.hide()
            el.mod_update.hide()

            fs = [self.curse.get_file(i) for i in proj.files]
            fs = [i for i in fs if self.instance.version in i.versions]
            fs.sort(key=lambda x: x.pub_time, reverse=True)

            if len(fs) > 0 and fs[0].pub_time > modf.pub_time:
                el.mod_update.show()

            self.ui.mod_box.addWidget(widget)

        self.ui.mod_box.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def setup_mod_browse(self, mods: list):
        clear_layout(self.ui.browse_box)
        for mod in mods:
            widget = QWidget()
            el = Ui_ModBrowseWidget()
            el.setupUi(widget)

            el.mod_name.setText(mod.name)
            el.mod_downloads.setText("Downloads: {}".format(human_format(mod.downloads)))
            el.mod_authors.setText("By {}".format(', '.join(mod.authors)))
            el.mod_desc.setText(mod.desc)
            el.mod_install.clicked.connect(partial(self.mod_install, mod))

            el.mod_more.clicked.connect(partial(webopen, mod.page))

            el.mod_icon.setStyleSheet(".QWidget { border-image: url(:/icons/OpenMineMods.svg); }")

            if mod.icon_name is not None:
                icon = path.join(self.icon_dir, mod.icon_name)
                if not path.isfile(icon):
                    icon_thread = QThread()
                    dltr = DownloaderThread()
                    dltr.moveToThread(icon_thread)
                    icon_thread.started.connect(
                        partial(dltr.download_file_raw, mod.icon_url, self.icon_dir, mod.icon_name))
                    dltr.done.connect(partial(el.mod_icon.setStyleSheet,
                                              ".QWidget { border-image: url(" +
                                              path.join(self.icon_dir, mod.icon_name) + "); }"))
                    icon_thread.start()
                    self.icon_threads.append(icon_thread)
                else:
                    el.mod_icon.setStyleSheet(".QWidget { border-image: url(" + icon + "); }")

            self.ui.browse_box.addWidget(widget)

        self.ui.browse_box.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def mod_install(self, mod: CurseProject, force_latest=False):
        files = [self.curse.get_file(i) for i in mod.files]
        fs = [i for i in files if self.instance.version in i.versions]
        if len(fs) < 1:
            return False

        fs.sort(key=lambda x: x.pub_time, reverse=True)
        if self.conf.read(Setting.ask_file) and not force_latest:
            dia = FileDialog(fs)
            f = dia.dia.exec_()
            if not f:
                return

            f = fs[f - 1]

        else:
            f = fs[0]

        dia = DownloadDialog()
        dia.download_mod(f, self.curse, self.instance)
        for dep in f.deps:
            if dep["Type"] != "required" or dep["AddOnId"] in self.installed_mods:
                continue
            self.mod_install(self.curse.get_project(dep["AddOnId"]))
        self.setup_mods()

    def mod_delete(self, fpath: str):
        def delete():
            self.instance.uninstall_mod(fpath)
            self.setup_mods()
        confirmation(self.win, delete, fpath)

    def mod_scan(self):
        self.instance.find_mods(self.curse.db)
        self.setup_mods()
