"""PlotBridge Mangrove, Tahap 6: pergeseran plot dan perbandingan NDVI.

Pasang sebagai pengganti plotbridge_mangrove.py di folder plugin QGIS.
Gunakan plotbridge_dialog.ui yang sudah dibuat di Qt Designer.

Cakupan tahap ini:
- Plot persegi 10 x 10 / 20 x 20 m, sejajar grid EPSG:32752.
- Raster NDVI siap pakai, satu band, north-up, CRS EPSG:32752.
- Nilai NDVI fisik -1 sampai 1; metadata scale/offset dihormati.
- NoData dan mask validitas GDAL diperiksa. Awan harus sudah dimask.
- Ekstraksi berjalan melalui QgsTask; layer hasil masih sementara.
- Tambahan Tahap 6 muncul otomatis; plotbridge_dialog.ui Tahap 5 tetap dipakai.
- Pergeseran DX/DY dalam meter membandingkan skenario ASAL dan GESER.
- NDVI asal dihitung ulang dari raster yang sama; selisih bukan persen.
- Fitur ini menguji sensitivitas posisi, bukan mengoreksi koordinat GPS.
- Belum mencakup pemilihan multiband, regresi, atau pencarian posisi optimum.
"""

from math import ceil, floor, hypot, isclose, isfinite
from pathlib import Path

import numpy as np

from qgis.PyQt import uic
from qgis.PyQt.QtGui import QAction
from qgis.PyQt.QtWidgets import (
    QBoxLayout, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)
from qgis.core import (
    Qgis, QgsApplication, QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsFillSymbol,
    QgsGeometry, QgsPointXY, QgsProject, QgsRasterLayer, QgsRendererCategory,
    QgsTask, QgsVectorLayer,
)


def pixel_window(bounds, transform, width, height):
    """Window GDAL (kolom, baris, lebar, tinggi), terpotong batas raster."""
    xmin, ymin, xmax, ymax = bounds
    x0, dx, rx, y0, ry, dy = transform
    if not all(isfinite(v) for v in transform):
        raise ValueError("Geotransform raster tidak valid.")
    if dx <= 0 or dy >= 0 or rx != 0 or ry != 0:
        raise ValueError("Tahap ini memerlukan raster north-up tanpa rotasi.")
    c0 = min(width, max(0, floor((xmin - x0) / dx)))
    c1 = min(width, max(0, ceil((xmax - x0) / dx)))
    r0 = min(height, max(0, floor((ymax - y0) / dy)))
    r1 = min(height, max(0, ceil((ymin - y0) / dy)))
    return c0, r0, max(0, c1 - c0), max(0, r1 - r0)


def weighted_ndvi(raw, mask, bounds, transform, column, row,
                  nodata=None, scale=1.0, offset=0.0):
    """Irisan eksak persegi sejajar grid dengan piksel, bukan mask biner."""
    xmin, ymin, xmax, ymax = bounds
    plot_area = (xmax - xmin) * (ymax - ymin)
    if plot_area <= 0:
        raise ValueError("Luas plot harus positif.")
    if not (isfinite(scale) and isfinite(offset)):
        raise ValueError("Scale atau offset raster tidak valid.")
    raw = np.asarray(raw, dtype=np.float64)
    mask = np.asarray(mask)
    if raw.ndim != 2 or mask.shape != raw.shape:
        raise ValueError("Ukuran data dan mask raster tidak sesuai.")

    x0, dx, _, y0, _, dy = transform
    columns = column + np.arange(raw.shape[1], dtype=np.float64)
    rows = row + np.arange(raw.shape[0], dtype=np.float64)
    left = x0 + columns * dx
    top = y0 + rows * dy
    overlap_x = np.maximum(0.0, np.minimum(xmax, left + dx)
                           - np.maximum(xmin, left))
    overlap_y = np.maximum(0.0, np.minimum(ymax, top)
                           - np.maximum(ymin, top + dy))
    areas = overlap_y[:, None] * overlap_x[None, :]
    valid = (areas > 0) & (mask != 0) & np.isfinite(raw)
    if nodata is not None:
        if np.isnan(nodata):
            valid &= ~np.isnan(raw)
        else:
            valid &= raw != nodata
    with np.errstate(over="ignore", invalid="ignore"):
        values = raw * scale + offset
    valid &= np.isfinite(values)
    if np.any(valid & ((values < -1.000001) | (values > 1.000001))):
        raise ValueError(
            "Ada nilai di luar rentang NDVI -1 sampai 1. "
            "Pilih raster NDVI siap pakai dengan scale/offset yang benar."
        )
    valid_area = float(areas[valid].sum())
    if valid_area <= 0:
        return (None, 0.0, 0.0, 0, "TANPA_DATA")
    mean = float(np.dot(values[valid], areas[valid]) / valid_area)
    percent = min(100.0, 100.0 * valid_area / plot_area)
    status = "LENGKAP" if percent >= 99.999999 else "SEBAGIAN"
    return mean, percent, valid_area, int(np.count_nonzero(valid)), status


def shifted_bounds(bounds, dx, dy):
    """Batas plot persegi 10/20 m setelah translasi, dalam koordinat UTM."""
    xmin, ymin, xmax, ymax = bounds
    if not all(isfinite(value) for value in (*bounds, dx, dy)):
        raise ValueError("Koordinat atau pergeseran tidak valid.")
    width, height = xmax - xmin, ymax - ymin
    if (not isclose(width, height, rel_tol=0.0, abs_tol=1e-6)
            or not any(isclose(width, side, rel_tol=0.0, abs_tol=1e-6)
                       for side in (10.0, 20.0))):
        raise ValueError("Gunakan plot persegi 10/20 m sejajar grid.")
    shifted = (xmin + dx, ymin + dy, xmax + dx, ymax + dy)
    if not all(isfinite(value) for value in shifted):
        raise ValueError("Hasil koordinat pergeseran tidak valid.")
    return shifted


def comparison_delta(original, shifted):
    """Selisih NDVI geser - asal; data tidak tersedia tetap NULL."""
    if original[0] is None or shifted[0] is None:
        return None, "TANPA_DATA"
    delta = float(shifted[0] - original[0])
    status = ("LENGKAP" if min(original[1], shifted[1]) >= 99.999999
              else "SEBAGIAN")
    return delta, status


def extract_worker(task, raster_path, plot_bounds):
    """Hanya data mandiri di worker; tidak mengakses layer atau widget GUI."""
    try:
        from osgeo import gdal
    except ImportError as error:
        raise RuntimeError("GDAL tidak tersedia dalam lingkungan Python QGIS.") from error
    source = gdal.Open(raster_path, gdal.GA_ReadOnly)
    if source is None:
        raise ValueError("Raster tidak dapat dibuka oleh GDAL.")
    try:
        if source.RasterCount != 1:
            raise ValueError("Tahap ini menerima raster NDVI satu band.")
        crs = QgsCoordinateReferenceSystem(source.GetProjectionRef())
        expected = QgsCoordinateReferenceSystem("EPSG:32752")
        if not crs.isValid() or crs != expected:
            raise ValueError("CRS raster harus EPSG:32752, sama dengan plot latihan.")
        transform = source.GetGeoTransform()
        band = source.GetRasterBand(1)
        scale = band.GetScale()
        offset = band.GetOffset()
        scale = 1.0 if scale is None else float(scale)
        offset = 0.0 if offset is None else float(offset)
        nodata = band.GetNoDataValue()
        mask_band = band.GetMaskBand()
        results = []
        for index, bounds in enumerate(plot_bounds):
            if task.isCanceled():
                return None
            col, row, width, height = pixel_window(
                bounds, transform, source.RasterXSize, source.RasterYSize,
            )
            if width == 0 or height == 0:
                statistics = (None, 0.0, 0.0, 0, "TANPA_DATA")
            else:
                raw = band.ReadAsArray(col, row, width, height)
                mask = mask_band.ReadAsArray(col, row, width, height)
                if raw is None or mask is None:
                    raise RuntimeError("Window raster atau mask gagal dibaca.")
                statistics = weighted_ndvi(
                    raw, mask, bounds, transform, col, row, nodata, scale, offset,
                )
            results.append(statistics)
            task.setProgress(100.0 * (index + 1) / len(plot_bounds))
        return results
    finally:
        source = None


class PlotBridgeMangrove:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self.menu_name = "&PlotBridge Mangrove"
        self.action = None
        self.dlg = None
        self.dlg_geser = None
        self.task = None
        self.plot_counter = 0
        self.ndvi_counter = 0
        self.shift_counter = 0
        self.enabled = False

    def initGui(self):
        self.enabled = True
        self.action = QAction(
            QgsApplication.getThemeIcon("/mActionAddPolygon.svg"),
            "PlotBridge Mangrove", self.iface.mainWindow(),
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu(self.menu_name, self.action)
        self.iface.addToolBarIcon(self.action)
        QgsProject.instance().layersAdded.connect(self.refresh_layers)
        QgsProject.instance().layersRemoved.connect(self.refresh_layers)

    def unload(self):
        self.enabled = False
        if self.task is not None:
            self.task.cancel()
        if self.dlg_geser is not None:
            self.dlg_geser.close()
            self.dlg_geser.deleteLater()
            self.dlg_geser = None
        project = QgsProject.instance()
        for signal in (project.layersAdded, project.layersRemoved):
            try:
                signal.disconnect(self.refresh_layers)
            except (TypeError, RuntimeError):
                pass
        if self.dlg is not None:
            self.dlg.close()
            self.dlg.deleteLater()
            self.dlg = None
        if self.action is not None:
            self.iface.removePluginMenu(self.menu_name, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

    def run(self):
        if self.dlg is None:
            dialog = None
            try:
                ui_path = self.plugin_dir / "plotbridge_dialog.ui"
                if not ui_path.is_file():
                    raise FileNotFoundError("plotbridge_dialog.ui tidak ditemukan.")
                dialog = QDialog(self.iface.mainWindow())
                uic.loadUi(str(ui_path), dialog)
                required = {
                    "spinX": QDoubleSpinBox, "spinY": QDoubleSpinBox,
                    "cmbUkuran": QComboBox, "lblStatus": QLabel,
                    "btnBuatPlot": QPushButton, "btnTutup": QPushButton,
                    "cmbPlotNDVI": QComboBox, "cmbRasterNDVI": QComboBox,
                    "btnEkstrakNDVI": QPushButton, "grpNDVI": QGroupBox,
                }
                missing = [name for name, kind in required.items()
                           if dialog.findChild(kind, name) is None]
                if missing:
                    raise ValueError("Periksa objectName dan Class di Qt Designer: "
                                     + ", ".join(missing))
                dialog.btnBuatPlot.clicked.connect(self.buat_plot)
                dialog.btnTutup.clicked.connect(dialog.close)
                dialog.btnEkstrakNDVI.clicked.connect(self.ekstrak_ndvi)
                self.add_shift_button(dialog)
                dialog.lblStatus.setWordWrap(True)
                dialog.lblStatus.setText("Siap. Tahap 6: ekstraksi NDVI dan pergeseran plot.")
                self.dlg = dialog
            except Exception as error:
                if dialog is not None:
                    dialog.deleteLater()
                QMessageBox.critical(self.iface.mainWindow(), "PlotBridge Mangrove", str(error))
                return
        self.refresh_layers()
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def add_shift_button(self, dialog):
        """Tambahkan satu tombol pada UI yang sudah dipakai di Tahap 5."""
        group = dialog.grpNDVI
        layout = group.layout()
        button = QPushButton("Pergeseran Plot (Tahap 6)", group)
        button.setObjectName("btnPergeseran")
        button.clicked.connect(self.open_shift_dialog)
        if isinstance(layout, QBoxLayout):
            layout.addWidget(button)
        elif isinstance(layout, QFormLayout):
            layout.addRow(button)
        elif isinstance(layout, QGridLayout):
            layout.addWidget(button, layout.rowCount(), 0, 1,
                             max(1, layout.columnCount()))
        else:
            button.deleteLater()
            raise ValueError("Terapkan Lay Out Vertically pada grpNDVI di Qt Designer.")
        dialog.btnPergeseran = button
        group.setMinimumHeight(group.minimumSizeHint().height())

    @staticmethod
    def is_source_plot(layer):
        """Hasil NDVI/geser, termasuk hasil tersimpan, bukan plot masukan."""
        return (isinstance(layer, QgsVectorLayer) and layer.isValid()
                and layer.geometryType() == Qgis.GeometryType.Polygon
                and layer.customProperty("plotbridge_role", "")
                not in ("ndvi_result", "shift_result")
                and layer.fields().indexFromName("ndvi_mean") < 0
                and layer.fields().indexFromName("skenario") < 0)

    @staticmethod
    def populate_combo(combo, layers, previous):
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("-- Pilih layer --", None)
            for layer in sorted(layers, key=lambda item: item.name().lower()):
                combo.addItem(layer.name(), layer.id())
            position = combo.findData(previous) if previous is not None else 0
            combo.setCurrentIndex(max(0, position))
        finally:
            combo.blockSignals(False)

    def refresh_layers(self, *unused):
        if self.dlg is None:
            return
        plot_id = self.dlg.cmbPlotNDVI.currentData()
        raster_id = self.dlg.cmbRasterNDVI.currentData()
        plots, rasters = [], []
        for layer in QgsProject.instance().mapLayers().values():
            if self.is_source_plot(layer):
                plots.append(layer)
            elif isinstance(layer, QgsRasterLayer) and layer.isValid():
                if layer.providerType() == "gdal" and layer.bandCount() == 1:
                    rasters.append(layer)
        for combo, layers, previous in (
            (self.dlg.cmbPlotNDVI, plots, plot_id),
            (self.dlg.cmbRasterNDVI, rasters, raster_id),
        ):
            self.populate_combo(combo, layers, previous)
        if self.dlg_geser is not None:
            for combo, layers in (
                (self.dlg_geser.cmbPlotGeser, plots),
                (self.dlg_geser.cmbRasterGeser, rasters),
            ):
                self.populate_combo(combo, layers, combo.currentData())

    def set_busy(self, busy):
        if self.dlg is not None:
            self.dlg.btnEkstrakNDVI.setEnabled(not busy)
        if self.dlg_geser is not None:
            self.dlg_geser.btnJalankanGeser.setEnabled(not busy)

    def show_error(self, error):
        if self.dlg is not None:
            self.dlg.lblStatus.setText(f"Gagal: {error}")
            if self.dlg_geser is not None and self.dlg_geser.isVisible():
                self.dlg_geser.lblGeserStatus.setText(f"Gagal: {error}")
            QMessageBox.critical(self.dlg, "PlotBridge Mangrove", str(error))

    def buat_plot(self):
        try:
            x, y = self.dlg.spinX.value(), self.dlg.spinY.value()
            if not (isfinite(x) and isfinite(y)):
                raise ValueError("Koordinat harus berupa angka valid.")
            choice = self.dlg.cmbUkuran.currentText().lower().replace(" ", "").replace("×", "x")
            sizes = {"10x10m": 10.0, "20x20m": 20.0}
            if choice not in sizes:
                raise ValueError("Pilih ukuran 10 x 10 m atau 20 x 20 m.")
            size = sizes[choice]
            half = size / 2.0
            ring = [QgsPointXY(x - half, y - half), QgsPointXY(x + half, y - half),
                    QgsPointXY(x + half, y + half), QgsPointXY(x - half, y + half),
                    QgsPointXY(x - half, y - half)]
            geometry = QgsGeometry.fromPolygonXY([ring])
            if geometry.isEmpty() or not geometry.isGeosValid():
                raise ValueError("Geometri plot tidak valid.")
            number = self.plot_counter + 1
            name = f"PlotBridge_{int(size)}x{int(size)}_{number:03d}"
            uri = ("Polygon?crs=EPSG:32752&field=plot_id:integer"
                   "&field=center_x:double(20,2)&field=center_y:double(20,2)"
                   "&field=size_m:double(10,2)&field=area_m2:double(20,2)"
                   "&field=area_ha:double(20,4)&field=crs:string(20)")
            layer = QgsVectorLayer(uri, name, "memory")
            if not layer.isValid():
                raise RuntimeError("Layer plot gagal dibuat.")
            feature = QgsFeature(layer.fields())
            feature.setGeometry(geometry)
            area = geometry.area()
            feature.setAttributes([number, x, y, size, area, area / 10000.0, "EPSG:32752"])
            success, added = layer.dataProvider().addFeatures([feature])
            if not success or len(added) != 1:
                raise RuntimeError("Plot gagal ditambahkan.")
            layer.updateExtents()
            QgsProject.instance().addMapLayer(layer)
            self.plot_counter = number
            self.dlg.cmbPlotNDVI.setCurrentIndex(self.dlg.cmbPlotNDVI.findData(layer.id()))
            self.dlg.lblStatus.setText(f"Berhasil: {name}; luas {area:.2f} m². Layer sementara.")
            self.iface.setActiveLayer(layer)
            self.iface.zoomToActiveLayer()
        except Exception as error:
            self.show_error(error)

    def ekstrak_ndvi(self):
        if self.task is not None:
            return
        try:
            project = QgsProject.instance()
            plot_id = self.dlg.cmbPlotNDVI.currentData()
            raster_id = self.dlg.cmbRasterNDVI.currentData()
            if not plot_id:
                raise ValueError("Pilih layer plot terlebih dahulu.")
            if not raster_id:
                raise ValueError("Pilih raster NDVI terlebih dahulu.")
            plot = project.mapLayer(plot_id)
            raster = project.mapLayer(raster_id)
            if not isinstance(plot, QgsVectorLayer) or not plot.isValid():
                raise ValueError("Pilih layer plot terlebih dahulu.")
            if not isinstance(raster, QgsRasterLayer) or not raster.isValid():
                raise ValueError("Pilih raster NDVI terlebih dahulu.")
            expected = QgsCoordinateReferenceSystem("EPSG:32752")
            if plot.crs() != expected or raster.crs() != expected:
                raise ValueError("Plot dan raster tahap ini harus sama-sama EPSG:32752.")
            if raster.bandCount() != 1 or raster.providerType() != "gdal":
                raise ValueError("Pilih raster NDVI satu band yang dibaca provider GDAL.")
            extra_uri = ("MultiPolygon?crs=EPSG:32752&field=ndvi_mean:double(20,6)"
                         "&field=valid_pct:double(20,4)&field=valid_m2:double(20,4)"
                         "&field=n_pix:integer&field=ndvi_band:integer"
                         "&field=ndvi_src:string&field=ndvi_status:string(20)")
            schema = QgsVectorLayer(extra_uri, "schema", "memory")
            extra_fields = [QgsField(field) for field in schema.fields()]
            collisions = [field.name() for field in extra_fields
                          if plot.fields().indexFromName(field.name()) >= 0]
            if collisions:
                raise ValueError("Pilih layer plot asal, bukan hasil ekstraksi NDVI sebelumnya.")
            geometries, attributes, bounds = [], [], []
            for feature in plot.getFeatures():
                geometry = feature.geometry()
                if geometry.isEmpty() or not geometry.isGeosValid():
                    raise ValueError(f"Geometri fitur {feature.id()} kosong atau tidak valid.")
                box = geometry.boundingBox()
                width, height = box.width(), box.height()
                rectangle_area = width * height
                if (not isclose(width, height, rel_tol=0.0, abs_tol=1e-6)
                        or not any(isclose(width, side, rel_tol=0.0, abs_tol=1e-6)
                                   for side in (10.0, 20.0))
                        or not isclose(geometry.area(), rectangle_area,
                                       rel_tol=1e-9, abs_tol=1e-6)):
                    raise ValueError("Gunakan plot persegi 10/20 m sejajar grid dari Tahap 4.")
                geometries.append(bytes(geometry.asWkb()))
                attributes.append(list(feature.attributes()))
                bounds.append((box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()))
            if not bounds:
                raise ValueError("Layer plot tidak memiliki fitur.")
            context = {
                "name": plot.name(), "geometries": geometries,
                "attributes": attributes, "fields": [QgsField(f) for f in plot.fields()],
                "extra_fields": extra_fields, "source": raster.source(),
            }
            task = QgsTask.fromFunction(
                "PlotBridge: ekstraksi NDVI berbobot luas", extract_worker,
                on_finished=lambda error, results=None: self.finish_ndvi(error, results, context),
                raster_path=raster.source(), plot_bounds=bounds,
            )
            self.task = task
            self.set_busy(True)
            self.dlg.lblStatus.setText(f"Memproses NDVI untuk {len(bounds)} plot...")
            QgsApplication.taskManager().addTask(task)
        except Exception as error:
            self.task = None
            if self.dlg is not None:
                self.set_busy(False)
            self.show_error(error)

    def finish_ndvi(self, error, results, context):
        self.task = None
        if not self.enabled or self.dlg is None:
            return
        self.set_busy(False)
        if error is not None:
            self.show_error(error)
            return
        if results is None:
            self.dlg.lblStatus.setText("Ekstraksi dibatalkan.")
            return
        try:
            self.ndvi_counter += 1
            name = f"PlotBridge_NDVI_{self.ndvi_counter:03d}"
            layer = QgsVectorLayer("MultiPolygon?crs=EPSG:32752", name, "memory")
            provider = layer.dataProvider()
            if not layer.isValid() or not provider.addAttributes(
                    context["fields"] + context["extra_fields"]):
                raise RuntimeError("Struktur layer hasil gagal dibuat.")
            layer.updateFields()
            features = []
            for wkb, attributes, statistics in zip(
                    context["geometries"], context["attributes"], results):
                geometry = QgsGeometry()
                geometry.fromWkb(wkb)
                geometry.convertToMultiType()
                mean, percent, area, pixels, status = statistics
                feature = QgsFeature(layer.fields())
                feature.setGeometry(geometry)
                feature.setAttributes(attributes + [mean, percent, area, pixels, 1,
                                                      context["source"], status])
                features.append(feature)
            success, added = provider.addFeatures(features)
            if not success or len(added) != len(features):
                raise RuntimeError("Sebagian fitur hasil gagal ditambahkan.")
            layer.updateExtents()
            layer.setCustomProperty("plotbridge_role", "ndvi_result")
            layer.setCustomProperty("plotbridge_source_plot", context["name"])
            QgsProject.instance().addMapLayer(layer)
            self.iface.setActiveLayer(layer)
            if len(results) == 1:
                mean, percent, _, _, status = results[0]
                value = "NULL" if mean is None else f"{mean:.6f}"
                message = f"{name}: NDVI {value}; area valid {percent:.2f}% ({status})."
            else:
                partial = sum(statistics[4] != "LENGKAP" for statistics in results)
                message = f"{name}: {len(results)} plot; {partial} plot tidak memiliki data lengkap."
            self.dlg.lblStatus.setText(message + " Buka tabel atribut; ekspor hasil ke GeoPackage.")
            self.iface.showAttributeTable(layer)
        except Exception as failure:
            self.show_error(failure)

    def open_shift_dialog(self):
        """Dialog Tahap 6 dibangun dari kode, tanpa mengubah file .ui."""
        if self.dlg_geser is None:
            dialog = QDialog(self.iface.mainWindow())
            dialog.setWindowTitle("PlotBridge Mangrove — Pergeseran Plot (Tahap 6)")
            dialog.resize(720, 390)
            layout = QVBoxLayout(dialog)
            info = QLabel(
                "Bandingkan posisi ASAL dan GESER dari plot yang sama. "
                "Semua fitur pada layer plot akan diproses. "
                "Pergeseran dalam meter pada EPSG:32752.", dialog,
            )
            info.setWordWrap(True)
            layout.addWidget(info)
            form = QFormLayout()
            dialog.cmbPlotGeser = QComboBox(dialog)
            dialog.cmbPlotGeser.setObjectName("cmbPlotGeser")
            dialog.cmbRasterGeser = QComboBox(dialog)
            dialog.cmbRasterGeser.setObjectName("cmbRasterGeser")
            dialog.spinDX = QDoubleSpinBox(dialog)
            dialog.spinDX.setObjectName("spinDX")
            dialog.spinDY = QDoubleSpinBox(dialog)
            dialog.spinDY.setObjectName("spinDY")
            for spin in (dialog.spinDX, dialog.spinDY):
                spin.setDecimals(2)
                spin.setRange(-1000000.0, 1000000.0)
                spin.setSingleStep(1.0)
                spin.setSuffix(" m")
                spin.setKeyboardTracking(False)
            dialog.spinDX.setValue(5.0)
            dialog.spinDY.setValue(0.0)
            form.addRow("Layer plot asal:", dialog.cmbPlotGeser)
            form.addRow("Raster NDVI — Band 1:", dialog.cmbRasterGeser)
            form.addRow("ΔX: Timur (+), Barat (−):", dialog.spinDX)
            form.addRow("ΔY: Utara (+), Selatan (−):", dialog.spinDY)
            layout.addLayout(form)
            dialog.lblGeserStatus = QLabel(
                "Siap. Pilih plot asal dan raster; isi ΔX/ΔY, lalu jalankan.", dialog,
            )
            dialog.lblGeserStatus.setObjectName("lblGeserStatus")
            dialog.lblGeserStatus.setWordWrap(True)
            layout.addWidget(dialog.lblGeserStatus)
            buttons = QHBoxLayout()
            dialog.btnJalankanGeser = QPushButton("Geser dan Bandingkan NDVI", dialog)
            dialog.btnJalankanGeser.setObjectName("btnJalankanGeser")
            dialog.btnJalankanGeser.clicked.connect(self.start_shift)
            close_button = QPushButton("Tutup", dialog)
            close_button.clicked.connect(dialog.close)
            buttons.addWidget(dialog.btnJalankanGeser)
            buttons.addWidget(close_button)
            layout.addLayout(buttons)
            self.dlg_geser = dialog
        self.refresh_layers()
        for target, source in (
            (self.dlg_geser.cmbPlotGeser, self.dlg.cmbPlotNDVI),
            (self.dlg_geser.cmbRasterGeser, self.dlg.cmbRasterNDVI),
        ):
            if source.currentData() is not None:
                position = target.findData(source.currentData())
                if position >= 0:
                    target.setCurrentIndex(position)
        self.set_busy(self.task is not None)
        self.dlg_geser.show()
        self.dlg_geser.raise_()
        self.dlg_geser.activateWindow()

    def start_shift(self):
        if self.task is not None:
            return
        try:
            dialog = self.dlg_geser
            dx, dy = dialog.spinDX.value(), dialog.spinDY.value()
            if not (isfinite(dx) and isfinite(dy)):
                raise ValueError("ΔX dan ΔY harus berupa angka valid.")
            if dx == 0.0 and dy == 0.0:
                raise ValueError("Isi ΔX atau ΔY dengan nilai selain nol.")
            project = QgsProject.instance()
            plot_id = dialog.cmbPlotGeser.currentData()
            raster_id = dialog.cmbRasterGeser.currentData()
            if not plot_id:
                raise ValueError("Pilih layer plot asal terlebih dahulu.")
            if not raster_id:
                raise ValueError("Pilih raster NDVI terlebih dahulu.")
            plot = project.mapLayer(plot_id)
            raster = project.mapLayer(raster_id)
            if not self.is_source_plot(plot):
                raise ValueError("Pilih layer plot asal, bukan layer hasil NDVI/pergeseran.")
            if not isinstance(raster, QgsRasterLayer) or not raster.isValid():
                raise ValueError("Pilih raster NDVI latihan terlebih dahulu.")
            expected = QgsCoordinateReferenceSystem("EPSG:32752")
            if plot.crs() != expected or raster.crs() != expected:
                raise ValueError("Plot dan raster tahap ini harus sama-sama EPSG:32752.")
            if raster.bandCount() != 1 or raster.providerType() != "gdal":
                raise ValueError("Pilih raster NDVI satu band yang dibaca provider GDAL.")
            entries, windows = [], []
            id_index = plot.fields().indexFromName("plot_id")
            for feature in plot.getFeatures():
                original = feature.geometry()
                if original.isEmpty() or not original.isGeosValid():
                    raise ValueError(f"Geometri fitur {feature.id()} kosong atau tidak valid.")
                box = original.boundingBox()
                bounds = (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum())
                shifted = shifted_bounds(bounds, dx, dy)
                area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
                if not isclose(original.area(), area, rel_tol=1e-9, abs_tol=1e-6):
                    raise ValueError("Gunakan plot persegi 10/20 m sejajar grid.")
                moved = QgsGeometry(original)
                outcome = moved.translate(dx, dy)
                if outcome != Qgis.GeometryOperationResult.Success:
                    raise RuntimeError(f"Pergeseran geometri fitur {feature.id()} gagal.")
                if moved.isEmpty() or not moved.isGeosValid():
                    raise ValueError("Geometri setelah pergeseran tidak valid.")
                moved_box = moved.boundingBox()
                actual = (moved_box.xMinimum(), moved_box.yMinimum(),
                          moved_box.xMaximum(), moved_box.yMaximum())
                if not all(isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
                           for a, b in zip(actual, shifted)):
                    raise RuntimeError("Batas geometri dan perhitungan raster tidak cocok.")
                if not isclose(moved.area(), area, rel_tol=1e-9, abs_tol=1e-6):
                    raise RuntimeError("Luas plot berubah saat pergeseran.")
                identifier = (str(feature.attribute(id_index)) if id_index >= 0
                              else str(feature.id()))
                entries.append({
                    "source_fid": str(feature.id()), "plot_id": identifier,
                    "bounds": bounds, "shifted": shifted, "area": area,
                    "geometry": bytes(original.asWkb()),
                    "moved_geometry": bytes(moved.asWkb()),
                })
                windows.extend((bounds, shifted))
            if not entries:
                raise ValueError("Layer plot tidak memiliki fitur.")
            context = {"entries": entries, "dx": dx, "dy": dy,
                       "source_plot": plot.name(), "source_raster": raster.source()}
            task = QgsTask.fromFunction(
                "PlotBridge: perbandingan NDVI posisi asal dan geser", extract_worker,
                on_finished=lambda error, results=None: self.finish_shift(error, results, context),
                raster_path=raster.source(), plot_bounds=windows,
            )
            self.task = task
            self.set_busy(True)
            message = f"Memproses {len(entries)} plot, masing-masing posisi ASAL dan GESER..."
            dialog.lblGeserStatus.setText(message)
            self.dlg.lblStatus.setText(message)
            QgsApplication.taskManager().addTask(task)
        except Exception as error:
            self.task = None
            self.set_busy(False)
            self.show_error(error)

    def finish_shift(self, error, results, context):
        self.task = None
        if not self.enabled or self.dlg is None:
            return
        self.set_busy(False)
        if error is not None:
            self.show_error(error)
            return
        if results is None:
            self.dlg.lblStatus.setText("Pergeseran dibatalkan.")
            if self.dlg_geser is not None:
                self.dlg_geser.lblGeserStatus.setText("Pergeseran dibatalkan.")
            return
        try:
            if len(results) != 2 * len(context["entries"]):
                raise RuntimeError("Jumlah hasil tidak sesuai dengan pasangan ASAL/GESER.")
            self.shift_counter += 1
            name = f"PlotBridge_Geser_{self.shift_counter:03d}"
            # Skema baru tidak menyalin fid asal sebagai primary key. Identitas
            # sumber disimpan pada src_fid; GeoPackage bebas membuat fid unik.
            specifications = (
                "src_layer:string", "src_fid:string(32)", "plot_id:string(80)",
                "skenario:string(10)", "x_asal:double(20,2)", "y_asal:double(20,2)",
                "center_x:double(20,2)", "center_y:double(20,2)",
                "size_m:double(10,2)", "area_m2:double(20,2)",
                "area_ha:double(20,4)", "crs:string(20)",
                "shift_dx:double(20,2)", "shift_dy:double(20,2)",
                "shift_m:double(20,2)", "ndvi_awal:double(20,6)",
                "ndvi_mean:double(20,6)", "delta_ndvi:double(20,6)",
                "valid0_pct:double(20,4)", "valid_pct:double(20,4)",
                "valid_m2:double(20,4)", "n_pix:integer", "ndvi_band:integer",
                "ndvi_src:string", "ndvi_status:string(20)", "cmp_status:string(20)",
            )
            uri = "MultiPolygon?crs=EPSG:32752" + "".join(
                "&field=" + specification for specification in specifications
            )
            layer = QgsVectorLayer(uri, name, "memory")
            if not layer.isValid():
                raise RuntimeError("Struktur layer pergeseran gagal dibuat.")
            features = []
            for index, entry in enumerate(context["entries"]):
                base, moved = results[2 * index:2 * index + 2]
                x0 = (entry["bounds"][0] + entry["bounds"][2]) / 2.0
                y0 = (entry["bounds"][1] + entry["bounds"][3]) / 2.0
                size = entry["bounds"][2] - entry["bounds"][0]
                for scenario, wkb, statistics, dx, dy in (
                    ("ASAL", entry["geometry"], base, 0.0, 0.0),
                    ("GESER", entry["moved_geometry"], moved,
                     context["dx"], context["dy"]),
                ):
                    geometry = QgsGeometry()
                    geometry.fromWkb(wkb)
                    if geometry.isEmpty():
                        raise RuntimeError("Geometri hasil tidak dapat dibaca.")
                    if not geometry.convertToMultiType():
                        raise RuntimeError("Konversi geometri hasil gagal.")
                    mean, percent, valid_area, pixels, status = statistics
                    delta, comparison = comparison_delta(base, statistics)
                    feature = QgsFeature(layer.fields())
                    feature.setGeometry(geometry)
                    feature.setAttributes([
                        context["source_plot"], entry["source_fid"], entry["plot_id"],
                        scenario, x0, y0, x0 + dx, y0 + dy, size, entry["area"],
                        entry["area"] / 10000.0, "EPSG:32752", dx, dy, hypot(dx, dy),
                        base[0], mean, delta, base[1], percent, valid_area, pixels, 1,
                        context["source_raster"], status, comparison,
                    ])
                    features.append(feature)
            success, added = layer.dataProvider().addFeatures(features)
            if not success or len(added) != len(features):
                raise RuntimeError("Sebagian fitur pergeseran gagal ditambahkan.")
            layer.updateExtents()
            symbols = (
                ("ASAL", "Posisi asal", {"color": "0,0,0,0",
                  "outline_color": "80,80,80,255", "outline_style": "dash",
                  "outline_width": "0.6"}),
                ("GESER", "Posisi geser", {"color": "39,104,181,55",
                  "outline_color": "39,104,181,255", "outline_style": "solid",
                  "outline_width": "0.6"}),
            )
            categories = [QgsRendererCategory(value, QgsFillSymbol.createSimple(style), label)
                          for value, label, style in symbols]
            layer.setRenderer(QgsCategorizedSymbolRenderer("skenario", categories))
            layer.setCustomProperty("plotbridge_role", "shift_result")
            layer.setCustomProperty("plotbridge_source_plot", context["source_plot"])
            QgsProject.instance().addMapLayer(layer)
            self.iface.setActiveLayer(layer)
            self.iface.zoomToActiveLayer()
            message = (f"{name}: {len(context['entries'])} pasangan ASAL/GESER. "
                       "Periksa ndvi_awal, ndvi_mean, delta_ndvi dan cmp_status. "
                       "Ekspor hasil ke GeoPackage untuk menyimpan.")
            self.dlg.lblStatus.setText(message)
            if self.dlg_geser is not None:
                self.dlg_geser.lblGeserStatus.setText(message)
            self.iface.showAttributeTable(layer)
        except Exception as failure:
            self.show_error(failure)
