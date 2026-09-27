import matplotlib
matplotlib.use("QT5Agg")
import sys
from PyQt5 import QtGui,QtCore
from PyQt5 import QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import UI
import os
try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class matplotlibWidget(QtWidgets.QWidget):
    """
    MUST Preceed "from window import *"
    """
    def __init__(self, parent = None):
        QtWidgets.QWidget.__init__(self, parent)
        self.canvas = MplCanvas()
        self.vbl = QtWidgets.QVBoxLayout()
        self.vbl.addWidget(self.canvas)
        self.setLayout(self.vbl)
from window import *


class GUI(QtWidgets.QMainWindow):
    """ Sets up Graphical User Interface for this Program. Requires PyQt4"""

    def __init__(self, parent=None):
        QtWidgets.QMainWindow.__init__(self, parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        from procedural_city_generation.additional_stuff.IOHelper import StdoutRedirector
        redirector=StdoutRedirector(self.ui.console,app)
        sys.stdout=redirector

        #### 1: ROADMAP ####
        UI.setRoadmapGUI(self)
        self.ui.roadmap_widget.hide()
        self.ui.roadmap_Run.clicked.connect(self.start_roadmap)
        self.createTable("roadmap")
        self.ui.roadmap_splitter.setSizes([90, 800])
        self.ui.roadmap_table.hide()

        #### 2: POLYGONS ####
        UI.setPolygonsGUI(self)
        self.ui.polygons_widget.hide()
        self.ui.polygons_Run.clicked.connect(self.start_polygons)
        self.createTable("polygons")
        self.ui.polygons_splitter.setSizes([90, 800])

        #### 3: BUILDING_GENERATION ####
        UI.setBuilding_generationGUI(self)
        self.ui.building_generation_widget.hide()
        self.ui.building_generation_Run.clicked.connect(self.start_building_generation)
        self.createTable("building_generation")
        self.ui.building_generation_splitter.setSizes([90, 800])

        #### 4: VISUALIZATION ####
        self.ui.visualization_Run.clicked.connect(UI.visualization)
        self.createTable("visualization")
        self.ui.visualization_splitter.setSizes([90, 800])

        #### 5: ADVANCED ####
        self.ui.clean_directories.clicked.connect(self.clean_directories)

        #### 6: EXPORT ####
        # (Tab is created in window.py)
        if hasattr(self.ui, "export_roads_button"):
            self.ui.export_roads_button.clicked.connect(self.export_roads)
        if hasattr(self.ui, "export_csv_button"):
            self.ui.export_csv_button.clicked.connect(self.export_csv)
        # export_buildings_button removed; buildings are controlled by a checkbox now
        if hasattr(self.ui, "scaleX_input") and hasattr(self.ui, "scaleY_input"):
            validator = QtGui.QDoubleValidator(0.000001, 1.0e12, 6, self)
            validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            self.ui.scaleX_input.setValidator(validator)
            self.ui.scaleY_input.setValidator(validator)

        sys.stderr=redirector
    


    #TODO Finish method
    def saveOptions(self, submodule="roadmap"):
        button=getattr(self.ui, submodule+"_save_button")
        table=getattr(self.ui, submodule+"_table")
        button.hide()
        table.hide()
     #   return saver
            
    def createTable(self, submodule):
        """ Creates the Options Table as PyQT4 Objects when called with a submodule. Very messy code, needs to be rewritten.
        Parameters
        ----------
        submodule: String, name of submodule
        """
	
	#Initial Pixel Width and Height of Options Table - should be replaced by getWindowSize()-like
        h=411
        w=891

        from procedural_city_generation.additional_stuff.Param import paramsFromJson, jsonFromParams
        from procedural_city_generation.additional_stuff.Singleton import Singleton
	
	#Load Parameters from .conf
        params=paramsFromJson(os.getcwd()+"/procedural_city_generation/inputs/"+submodule+".conf")
        
	#Add Buttons and assign functions
        table=QtWidgets.QTableWidget(getattr(self.ui, submodule+"_frame"))
        save_button=QtWidgets.QPushButton(getattr(self.ui, submodule+"_frame"), text="Save")
        save_button.setGeometry(QtCore.QRect(w-100, h, 100, 31))
        save_button.hide()
        default_button=QtWidgets.QPushButton(getattr(self.ui, submodule+"_frame"), text="Reset Defaults")
        default_button.setGeometry(QtCore.QRect(w-260, h, 150, 31))
        default_button.hide()
        table.hide()

	#Set Table Geometry, code looks repetitive and should be reworked
        table.setGeometry(QtCore.QRect(0, 0, w, h))
        table.setColumnCount(6)
        table.setHorizontalHeaderItem(0, QtWidgets.QTableWidgetItem("Parameter Name"))
        table.setColumnWidth(0, int(0.2*w))
        table.setHorizontalHeaderItem(1, QtWidgets.QTableWidgetItem("Description"))
        table.setColumnWidth(1, int(0.5*w))
        table.setHorizontalHeaderItem(2, QtWidgets.QTableWidgetItem("Default Value"))
        table.setColumnWidth(2, int(0.125*w))
        table.setHorizontalHeaderItem(3, QtWidgets.QTableWidgetItem("Value"))
        table.setColumnWidth(3, int(0.125*w))
        table.setHorizontalHeaderItem(4, QtWidgets.QTableWidgetItem("min"))
        table.setColumnWidth(4, int(0.1*w))
        table.setHorizontalHeaderItem(5, QtWidgets.QTableWidgetItem("max"))
        table.setColumnWidth(5, int(0.1*w))
        table.setRowCount(len(params))
	
	#Fill out Table with Parameters. Code Looks repetitive, should be reworked
        i=0
        for parameter in params:
            g=QtWidgets.QTableWidgetItem(str(parameter.name) )
            g.setFlags( g.flags() & ~QtCore.Qt.ItemIsEditable )
            g.setBackground(QtGui.QBrush(QtGui.QColor(235, 235, 235)))
            table.setItem( i, 0 , g)
             
            g=QtWidgets.QTableWidgetItem(str(parameter.description))
            g.setFlags( g.flags() & ~QtCore.Qt.ItemIsEditable)
            g.setBackground(QtGui.QBrush(QtGui.QColor(235, 235, 235)))
            table.setItem( i, 1 , g)
             
            g=QtWidgets.QTableWidgetItem(str(parameter.default))
            g.setFlags( g.flags() & ~QtCore.Qt.ItemIsEditable)
            g.setBackground(QtGui.QBrush(QtGui.QColor(235, 235, 235)))
            table.setItem( i, 2 , g)
             
            g=QtWidgets.QTableWidgetItem(str(parameter.value))
            table.setItem( i, 3 , g)

            s = "" if parameter.value_lower_bound is None else str(parameter.value_lower_bound)
            g=QtWidgets.QTableWidgetItem(s)
            g.setFlags( g.flags() & ~QtCore.Qt.ItemIsEditable)
            g.setBackground(QtGui.QBrush(QtGui.QColor(235, 235, 235)))
            table.setItem( i, 4 , g)

            s = "" if parameter.value_upper_bound is None else str(parameter.value_upper_bound)
            g=QtWidgets.QTableWidgetItem(s)
            g.setFlags( g.flags() & ~QtCore.Qt.ItemIsEditable)
            g.setBackground(QtGui.QBrush(QtGui.QColor(235, 235, 235)))
            table.setItem( i, 5 , g)
            i+=1


	#Connect functions to buttons
        getattr(self.ui, submodule+"_Options").clicked.connect(table.show)
        getattr(self.ui, submodule+"_Options").clicked.connect(save_button.show)
        getattr(self.ui, submodule+"_Options").clicked.connect(default_button.show)
        setattr(self.ui, submodule+"_table", table)

        def save_params():
            for i, param in enumerate(params):
                it=table.item(i, 3).text()
                try:
                    it=eval(str(it))
                except:
                    it=str(it)
                param.setValue(it)
                Singleton(submodule).kill()
            jsonFromParams(os.getcwd()+"/procedural_city_generation/inputs/"+submodule+".conf", params)
            print("Save successful")
            save_button.hide()
            default_button.hide()
            table.hide()
            print(UI.donemessage)

        save_button.clicked.connect(save_params)
        setattr(self.ui, submodule+"_save_button", save_button)

        def default_params():
            for i, param in enumerate(params):
                table.item(i, 3).setText(_fromUtf8(str(param.default)))


        default_button.clicked.connect(default_params)
        setattr(self.ui, submodule+"_default_button", default_button)



    def plot(self, x, y, linewidth=1, color="red"):
        self.active_widget.canvas.ax.plot(x, y, linewidth=linewidth, color=color)
       
    def clear(self):
        self.active_widget.canvas.ax.clear()
                
    def start_roadmap(self):
        self.active_widget=self.ui.roadmap_widget
        self.active_widget.show()
        self.clear()
        UI.roadmap()
        
    def start_polygons(self):
        self.active_widget=self.ui.polygons_widget
        self.active_widget.show()
        self.clear()
        UI.polygons()

    def start_building_generation(self):
        self.active_widget=self.ui.building_generation_widget
        self.active_widget.show()
        self.clear()
        UI.building_generation()

    def clean_directories(self):
        from procedural_city_generation.additional_stuff.clean_tools import clean_pyc_files
        print("removing all .pyc files")
        clean_pyc_files(os.getcwd())
        print("removing all items in /procedural_city_generation/temp/ directory")
        os.system("rm -f " +os.getcwd()+"/procedural_city_generation/temp/*")
        print("removing all items in /procedural_city_generation/outputs/ directory")
        os.system("rm -f " +os.getcwd()+"/procedural_city_generation/outputs/*")
        print(UI.donemessage)
        
    def set_xlim(self, tpl):
        self.active_widget.canvas.ax.set_xlim(tpl)
        
    def set_ylim(self, tpl):
        self.active_widget.canvas.ax.set_ylim(tpl)
        
    def update(self):
        self.active_widget.canvas.draw()
        global app
        app.processEvents()

    def _prepare_export_data(self):
        from procedural_city_generation.additional_stuff.Singleton import Singleton
        from procedural_city_generation.additional_stuff import pickletools
        import procedural_city_generation
        import os
        import pickle

        path = os.path.dirname(procedural_city_generation.__file__)

        vertex_list = None
        roadmap_singleton = Singleton("roadmap")
        roadmap_name = getattr(roadmap_singleton, "output_name", None) or "output"
        vertex_list = pickletools.reconstruct(roadmap_name)

        polygons = []
        polys_name = None

        bgen_singleton = Singleton("building_generation")
        bgen_name = getattr(bgen_singleton, "output_name", None)
        if bgen_name:
            bgen_pickle = os.path.join(path, "temp", f"{bgen_name}_polygons.txt")
            if os.path.exists(bgen_pickle):
                with open(bgen_pickle, "rb") as f:
                    polygons = pickle.loads(f.read())

        if not polygons:
            polys_singleton = Singleton("polygons")
            polys_name = getattr(polys_singleton, "input_name", None)
            if polys_name:
                poly_pickle = os.path.join(path, "temp", f"{polys_name}_polygons.txt")
                if os.path.exists(poly_pickle):
                    with open(poly_pickle, "rb") as f:
                        polygons = pickle.loads(f.read())

        def _read_scale(line_edit):
            if line_edit is None:
                return None
            text = line_edit.text().strip()
            if not text:
                return None
            try:
                value = float(text)
            except ValueError:
                return None
            if value <= 0:
                return None
            return value

        scale_x = _read_scale(getattr(self.ui, "scaleX_input", None))
        scale_y = _read_scale(getattr(self.ui, "scaleY_input", None))

        def _collect_points(verts, polys):
            points = []
            for v in verts or []:
                try:
                    points.append((float(v.coords[0]), float(v.coords[1])))
                except Exception:
                    continue
            for poly in polys or []:
                verts_list = getattr(poly, "vertices", None) or []
                for vx, vy in verts_list:
                    points.append((float(vx), float(vy)))
            return points

        def _normalize(value, min_v, max_v, scale):
            if scale is None:
                return value
            if max_v <= min_v:
                return 0.0
            return (value - min_v) / (max_v - min_v) * scale

        points = _collect_points(vertex_list, polygons)
        if points and (scale_x is not None or scale_y is not None):
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)

            class _VertexProxy:
                def __init__(self, src, coords):
                    self.coords = coords
                    if hasattr(src, "selfindex"):
                        self.selfindex = src.selfindex
                    if hasattr(src, "minor_road"):
                        self.minor_road = src.minor_road
                    self.neighbours = []

            proxy_by_id = {}
            normalized_vertices = []
            for v in vertex_list or []:
                nx = _normalize(float(v.coords[0]), min_x, max_x, scale_x)
                ny = _normalize(float(v.coords[1]), min_y, max_y, scale_y)
                proxy = _VertexProxy(v, [nx, ny])
                proxy_by_id[id(v)] = proxy
                normalized_vertices.append(proxy)

            for v in vertex_list or []:
                proxy = proxy_by_id.get(id(v))
                if proxy is None:
                    continue
                neighbours = []
                for n in getattr(v, "neighbours", []) or []:
                    p = proxy_by_id.get(id(n))
                    if p is not None:
                        neighbours.append(p)
                proxy.neighbours = neighbours

            class _PolyProxy:
                def __init__(self, src, vertices):
                    self.vertices = vertices
                    if hasattr(src, "poly_type"):
                        self.poly_type = src.poly_type
                    if hasattr(src, "name"):
                        self.name = src.name
                    if hasattr(src, "floors"):
                        self.floors = src.floors

            normalized_polygons = []
            for poly in polygons or []:
                verts_list = getattr(poly, "vertices", None) or []
                scaled = []
                for vx, vy in verts_list:
                    nx = _normalize(float(vx), min_x, max_x, scale_x)
                    ny = _normalize(float(vy), min_y, max_y, scale_y)
                    scaled.append((nx, ny))
                normalized_polygons.append(_PolyProxy(poly, scaled))

            vertex_list = normalized_vertices
            polygons = normalized_polygons

        export_name = roadmap_name if vertex_list else (polys_name or "output")
        merge_roads = bool(getattr(getattr(self.ui, "merge_roads_checkbox", None), "isChecked", lambda: False)())
        export_buildings = bool(
            getattr(getattr(self.ui, "export_buildings_checkbox", None), "isChecked", lambda: True)()
        )
        return {
            "path": path,
            "export_name": export_name,
            "vertex_list": vertex_list or [],
            "polygons": polygons or [],
            "merge_roads": merge_roads,
            "export_buildings": export_buildings,
        }

    def export_roads(self):
        """Export junctions, roads, and (optionally) buildings to a combined JSON file."""
        try:
            from procedural_city_generation.export.city_json import export_city_json
            export_data = self._prepare_export_data()
            out_dir = os.path.join(export_data["path"], "outputs")
            out_path = os.path.join(out_dir, f"{export_data['export_name']}_city.json")
            export_city_json(
                export_data["vertex_list"],
                export_data["polygons"],
                out_path,
                merge_roads=export_data["merge_roads"],
                export_buildings=export_data["export_buildings"],
            )
            print(f"City JSON exported:\n  {out_path}")
            print(UI.donemessage)
        except Exception:
            import traceback
            traceback.print_exc()
            print(UI.errormessage)

    def export_csv(self):
        """Export junctions, edges, roads, and buildings as CSV files."""
        try:
            from procedural_city_generation.export.city_csv import export_city_csv
            export_data = self._prepare_export_data()
            out_dir = os.path.join(export_data["path"], "outputs", f"{export_data['export_name']}_csv")
            written = export_city_csv(
                export_data["vertex_list"],
                export_data["polygons"],
                out_dir,
                merge_roads=export_data["merge_roads"],
                export_buildings=export_data["export_buildings"],
            )
            print("City CSV exported:")
            for name in ["nodes", "edges", "roads", "buildings", "buildings_shape"]:
                print(f"  {name}: {written[name]}")
            print(UI.donemessage)
        except Exception:
            import traceback
            traceback.print_exc()
            print(UI.errormessage)

class FigureSaver:
    class __FigureSaver:
        def __init__(self, fig=None):
            self.plot=fig.plot
            self.show=fig.show
    instance=None

    def __init__(self, fig=None):
        if not FigureSaver.instance and (fig is not None):
            FigureSaver.instance=FigureSaver.__FigureSaver(fig)


    def __getattr__(self, name):
        return getattr(self.instance, name)

    def __setattr__(self, name, value):
        setattr(self.instance, name, value)

class MplCanvas(FigureCanvas):

    def __init__(self):
        self.fig = Figure(frameon=False)
        self.ax = self.fig.add_subplot(111)
        self.ax.get_yaxis().set_visible(False)
        self.ax.get_xaxis().set_visible(False)
        FigureCanvas.__init__(self, self.fig)
        FigureCanvas.setSizePolicy(self, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)





if __name__  ==  "__main__":
    global app
    app = QtWidgets.QApplication(sys.argv)
    myapp = GUI()
    myapp.show()
    app.exec_()
