# PlotBridge Mangrove

A QGIS plugin for creating 10 × 10 m and 20 × 20 m square plots, extracting area-weighted mean NDVI from a prepared single-band raster, and comparing original and translated plot positions. The current workflow uses EPSG:32752 and reports valid-data coverage, NDVI differences, and source identifiers.

## Ringkasan

PlotBridge Mangrove membantu membandingkan NDVI pada posisi awal plot lapangan dan pada posisi yang digeser dengan jarak tertentu. Pengguna dapat membuat plot persegi, mengekstrak rata-rata NDVI, dan menghasilkan pasangan fitur ASAL–GESER dari raster yang sama.

Nama Mangrove menunjukkan sasaran penggunaan. Perhitungan yang tersedia adalah ekstraksi NDVI dan uji sensitivitas posisi plot; klasifikasi mangrove dan validasi terhadap pengukuran vegetasi lapangan belum tersedia.

Informasi versi plugin, versi minimum QGIS yang dinyatakan, penulis, dan tautan proyek terdapat dalam **metadata.txt**. Dukungan versi QGIS harus mengacu pada versi yang benar-benar sudah diuji oleh pengembang. Publikasi awal disarankan sebagai rilis **experimental**.

## Fungsi yang tersedia

- Membuat satu plot persegi per penggunaan tombol pembuatan plot, dengan sisi 10 m atau 20 m.
- Menghitung rata-rata NDVI dengan bobot luas irisan plot dan piksel.
- Memeriksa NoData, nilai tidak berhingga, mask validitas GDAL, serta metadata scale/offset.
- Melaporkan luas dan persentase plot yang tercakup data valid.
- Menggeser semua fitur pada layer plot masukan menggunakan ΔX dan ΔY dalam meter.
- Menghitung ulang NDVI posisi awal dan posisi geser dari raster yang sama.
- Membuat dua fitur hasil per plot: **ASAL** dan **GESER**.
- Mencatat identitas sumber, koordinat pusat, besar pergeseran, nilai NDVI, dan status data.
- Mempertahankan layer plot masukan. Hasil ditambahkan sebagai layer baru yang sementara.

## Persyaratan

Plugin dijalankan di dalam QGIS Desktop. Dependensi yang digunakan adalah PyQGIS/PyQt, NumPy, dan binding Python GDAL (**osgeo.gdal**) dalam lingkungan Python QGIS.

Gunakan paket plugin yang kompatibel dengan versi QGIS yang dipakai. Nomor versi minimum pada metadata harus diverifikasi sebelum rilis; panduan ini tidak menyatakan dukungan untuk seluruh versi QGIS atau seluruh sistem operasi.

### Koordinat dan plot

| Parameter | Persyaratan versi sekarang |
|---|---|
| CRS plot dan raster | **EPSG:32752 — WGS 84 / UTM zone 52S** |
| Input X | Easting UTM, dalam meter |
| Input Y | Northing UTM, dalam meter |
| Makna X/Y | Titik pusat plot |
| Ukuran plot | 10 × 10 m atau 20 × 20 m |
| Bentuk dan orientasi | Persegi tanpa rotasi, sejajar sumbu koordinat |
| Layer plot masukan | Poligon valid dengan setidaknya satu fitur yang memenuhi ukuran dan bentuk tersebut |

Latitude/longitude dan derajat–menit–detik belum dikonversi secara otomatis oleh plugin. Ubah koordinat sumber ke EPSG:32752 terlebih dahulu, kemudian gunakan X/Y hasil transformasi. Mengubah CRS tampilan proyek atau sekadar menetapkan ulang label CRS tidak sama dengan mentransformasikan koordinat.

EPSG:32752 bukan CRS umum untuk semua wilayah. Versi ini membatasi pemrosesan pada CRS tersebut.

### Raster

| Parameter | Persyaratan versi sekarang |
|---|---|
| Isi raster | NDVI yang sudah dihitung |
| Jumlah band | Tepat satu band |
| Provider | GDAL, misalnya GeoTIFF yang dibaca melalui GDAL |
| CRS | EPSG:32752, sama dengan plot |
| Orientasi | North-up, tanpa rotasi grid |
| Nilai fisik NDVI | -1 sampai 1 setelah penerapan scale/offset |
| NoData dan awan | NoData/mask harus benar; penyaringan awan disiapkan sebelum pemrosesan |

**Band 1 pada antarmuka adalah band tunggal file hasil NDVI.** Istilah ini tidak berarti Band 1 asli citra satelit.

Plugin belum menghitung NDVI dari band merah dan NIR. Siapkan NDVI terlebih dahulu, lalu pilih raster hasilnya. File citra multiband belum diterima. Jika ada beberapa raster NDVI, pilih satu raster untuk setiap proses.

Nilai reflektansi satu band satelit bukan NDVI. Jumlah band yang sesuai saja tidak membuktikan bahwa sebuah raster berisi NDVI.

## Instalasi dari ZIP

1. Siapkan ZIP plugin dengan satu folder utama **plotbridge_mangrove** di dalamnya.
2. Folder itu harus menyertakan metadata.txt, __init__.py, plotbridge_mangrove.py, plotbridge_dialog.ui, LICENSE, dan README.md. Sertakan pula setiap sumber daya tambahan yang benar-benar digunakan oleh paket.
3. Di QGIS, buka **Plugins → Manage and Install Plugins**.
4. Pilih **Install from ZIP**, kemudian pilih ZIP plugin dan jalankan instalasi.
5. Pastikan PlotBridge Mangrove aktif pada daftar plugin yang terpasang.
6. Buka plugin melalui menu **Plugins → PlotBridge Mangrove** atau ikon toolbar yang disediakan.

Uji pemasangan ZIP pada profil QGIS baru sebelum publikasi. Keberhasilan plugin dalam profil pengembangan belum membuktikan bahwa semua berkas instalasi telah masuk ke ZIP.

## Membuat plot

1. Buka PlotBridge Mangrove.
2. Masukkan X dan Y pusat plot dalam EPSG:32752, dengan satuan meter.
3. Pilih ukuran 10 × 10 m atau 20 × 20 m.
4. Jalankan tombol pembuatan plot.
5. Pastikan layer plot muncul dan memiliki satu fitur pada tabel atribut.
6. Periksa area_m2: plot 10 × 10 m memiliki luas 100 m²; plot 20 × 20 m memiliki luas 400 m².

Contoh nama layer yang dibuat adalah **PlotBridge_10x10_001** atau **PlotBridge_20x20_001**. Nomor dapat berubah sesuai urutan proses.

Layer masih sementara. Ekspor layer untuk menyimpannya secara permanen.

## Mengekstrak NDVI

1. Tambahkan raster NDVI siap pakai ke proyek QGIS.
2. Pastikan raster dan plot benar-benar berada dalam EPSG:32752.
3. Pada bagian ekstraksi NDVI, pilih **layer plot asal**.
4. Pilih **raster NDVI satu band**.
5. Jalankan tombol ekstraksi NDVI dan tunggu sampai status proses selesai.
6. Buka tabel atribut layer hasil, misalnya **PlotBridge_NDVI_001**.
7. Periksa ndvi_mean, valid_pct, valid_m2, n_pix, dan ndvi_status.
8. Ekspor hasil ke GeoPackage jika ingin menyimpannya.

Ekstraksi memproses semua fitur pada layer masukan yang memenuhi persyaratan. Gunakan layer plot asal untuk proses berikutnya; layer hasil ekstraksi tidak digunakan kembali sebagai layer plot asal.

### Cara rata-rata dihitung

Setiap piksel valid berkontribusi menurut luas bagian piksel yang berada di dalam plot:

**ndvi_mean = jumlah(luas irisan valid × nilai NDVI) / jumlah(luas irisan valid)**

Bagian tanpa data tidak diisi dengan NDVI nol. Persentase cakupan dihitung terhadap luas penuh plot, sehingga bagian plot di luar raster atau pada NoData menurunkan valid_pct.

Jika tidak ada luas yang tercakup data valid, ndvi_mean tetap **NULL/kosong**.

## Pergeseran dan perbandingan NDVI

1. Buka **Pergeseran Plot (Tahap 6)**.
2. Pilih **Layer plot asal** yang memiliki fitur.
3. Pilih raster NDVI yang memenuhi persyaratan.
4. Isi ΔX dan ΔY dalam meter.
5. Klik **Geser dan Bandingkan NDVI**.
6. Tunggu sampai proses selesai.
7. Buka tabel atribut layer hasil, misalnya **PlotBridge_Geser_001**.
8. Periksa pasangan ASAL/GESER untuk setiap plot dan simpan hasilnya.

| Parameter | Positif | Negatif |
|---|---|---|
| ΔX | Timur | Barat |
| ΔY | Utara | Selatan |

Contoh: ΔX = 5 m dan ΔY = 0 m menggeser plot 5 m ke timur. Kedua nilai tidak boleh sama-sama nol.

Semua fitur layer asal diproses. Satu fitur masukan menghasilkan dua fitur keluaran; N fitur masukan menghasilkan 2N fitur keluaran.

NDVI awal dihitung ulang dari raster yang dipilih pada proses pergeseran. Layer asal tetap dipertahankan, sedangkan geometri hasil geser mempunyai ukuran dan luas yang sama dengan plot awal.

## Membaca hasil

| Kolom | Arti |
|---|---|
| plot_id | Identitas plot |
| skenario | ASAL atau GESER pada hasil perbandingan |
| src_layer, src_fid | Identitas layer dan fitur masukan pada hasil perbandingan |
| x_asal, y_asal | Koordinat pusat plot awal |
| center_x, center_y | Koordinat pusat fitur hasil |
| size_m | Panjang sisi plot, dalam meter |
| area_m2, area_ha | Luas plot dalam m² dan hektare |
| crs | CRS yang digunakan |
| shift_dx, shift_dy | Pergeseran fitur hasil dalam meter; fitur ASAL memiliki pergeseran nol |
| shift_m | Jarak pergeseran, dihitung dari ΔX dan ΔY |
| ndvi_awal | Rata-rata NDVI plot asal |
| ndvi_mean | Rata-rata NDVI fitur yang bersangkutan |
| delta_ndvi | ndvi_mean dikurangi ndvi_awal pada hasil perbandingan |
| valid0_pct | Persentase cakupan data valid pada posisi asal |
| valid_pct | Persentase luas fitur yang tercakup data valid |
| valid_m2 | Luas irisan dengan data valid, dalam m² |
| n_pix | Jumlah piksel valid dengan luas irisan lebih besar dari nol |
| ndvi_band | Band raster yang dibaca; bernilai 1 pada versi sekarang |
| ndvi_src | Sumber raster yang digunakan |
| ndvi_status | Status cakupan data fitur |
| cmp_status | Status ketersediaan data untuk perbandingan asal dan fitur hasil |

Sebagian kolom hanya tersedia pada hasil pergeseran. Layer hasil ekstraksi biasa mempertahankan atribut masukan dan menambahkan kolom statistik NDVI.

Status yang tersedia:

- **LENGKAP:** seluruh luas tercakup data valid, dengan toleransi numerik.
- **SEBAGIAN:** hanya sebagian luas tercakup data valid.
- **TANPA_DATA:** tidak ada data valid untuk statistik yang diperlukan.

cmp_status mempertimbangkan ketersediaan data pada kedua posisi yang dibandingkan. delta_ndvi tetap NULL jika salah satu nilai NDVI yang diperlukan tidak tersedia.

**valid_pct = 100 berarti cakupan data valid penuh.** Angka tersebut tidak mengukur akurasi GPS, akurasi posisi citra, atau ketepatan ilmiah sebesar 100%.

delta_ndvi adalah selisih nilai indeks, **bukan persen**. Contoh: 0,80 menjadi 0,50 menghasilkan delta_ndvi = -0,30.

## Menyimpan hasil ke GeoPackage

1. Pilih layer hasil yang akan disimpan.
2. Klik kanan layer, kemudian pilih **Export → Save Features As**.
3. Pilih format **GeoPackage**.
4. Tentukan nama file dengan ekstensi .gpkg dan nama layer yang jelas.
5. Pertahankan CRS EPSG:32752.
6. Simpan semua fitur jika ingin mempertahankan seluruh pasangan ASAL/GESER.
7. Buka kembali hasil tersimpan dan periksa jumlah fitur serta kolomnya.

Contoh nama layer: **ndvi_plot_10m** atau **perbandingan_20m_dx5_dy0**.

Menyimpan proyek QGIS tidak menggantikan ekspor layer sementara ke file data.

## Acuan uji latihan

Contoh berikut menggunakan raster sintetis berpiksel 10 m, satu piksel pusat bernilai 0,8 dan piksel sekitarnya bernilai 0,2. Plot awal berpusat pada piksel 0,8, seluruh cakupan valid, dan pergeseran adalah ΔX = 5 m, ΔY = 0 m.

| Ukuran plot | NDVI awal | NDVI setelah geser | delta_ndvi |
|---|---:|---:|---:|
| 10 × 10 m | 0,80 | 0,50 | -0,30 |
| 20 × 20 m | 0,35 | 0,35 | 0,00 |

Hasil tersebut berlaku untuk susunan raster latihan yang dijelaskan. Nilai pada citra nyata bergantung pada posisi, nilai piksel, resolusi, dan cakupan data valid.

Uji sintetis memeriksa perhitungan dasar. Validasi citra nyata, pemasangan pada profil baru, dan dukungan versi/sistem operasi masih perlu dilakukan sebelum mengklaim kesiapan rilis stabil.

## Masalah yang sering dijumpai

| Gejala atau pesan | Pemeriksaan |
|---|---|
| Layer plot tidak memiliki fitur | Buka tabel atribut layer asal dan pastikan jumlah fitur lebih dari nol. |
| Raster tidak muncul dalam pilihan NDVI | Periksa bahwa raster memiliki tepat satu band dan provider GDAL. |
| CRS tidak sesuai | Transformasikan data sumber ke EPSG:32752; jangan hanya mengganti label CRS. |
| Ada nilai di luar rentang NDVI | Pastikan input benar-benar NDVI dan metadata scale/offset benar. |
| Hasil NULL atau TANPA_DATA | Periksa irisan plot dengan raster, NoData, dan mask validitas. |
| Hasil SEBAGIAN | Periksa valid_pct; sebagian luas berada pada NoData atau di luar raster. |
| Layer hasil tidak muncul dalam pilihan plot asal | Pilih layer plot sebelum ekstraksi/pergeseran. Hasil sengaja dikecualikan sebagai masukan plot. |
| delta_ndvi bernilai nol | Periksa susunan nilai piksel dan cakupan data. Pergeseran dapat menghasilkan rata-rata yang tetap sama. |
| Hasil hilang ketika proyek dibuka kembali | Ekspor layer sementara ke GeoPackage dan gunakan layer tersimpan. |

## Batasan versi sekarang

- CRS ditetapkan pada EPSG:32752; pemilihan dan transformasi CRS otomatis belum tersedia.
- Pembuatan plot menggunakan X/Y satu pusat per proses; impor CSV langsung dan pembuatan plot massal belum tersedia.
- Bentuk plot dibatasi pada persegi 10 m atau 20 m yang sejajar sumbu koordinat.
- Input dibatasi pada satu raster NDVI satu band per proses; pemilihan multiband dan perhitungan NDVI dari band satelit belum tersedia.
- Grid raster berotasi belum didukung.
- Penyaringan awan harus dilakukan sebelum memasukkan raster.
- Satu pasangan ΔX/ΔY dijalankan setiap proses; rangkaian banyak arah/jarak belum otomatis.
- Penyimpanan hasil dilakukan melalui ekspor QGIS.
- Pergeseran merupakan uji sensitivitas posisi, bukan penentuan koordinat GPS yang benar.
- Pembobotan luas tidak meningkatkan resolusi spasial asli citra.
- Regresi, pencarian posisi optimum, dan klasifikasi mangrove belum tersedia.

## Pelaporan masalah

Gunakan issue tracker yang dicantumkan pada metadata proyek. Sertakan versi QGIS, sistem operasi, pesan kesalahan, CRS, jumlah band, ukuran plot, ΔX/ΔY jika digunakan, serta langkah untuk mengulang masalah. Sertakan contoh data kecil jika dapat dibagikan.

## Lisensi

**GPL-3.0-or-later — GNU General Public License versi 3 atau versi lebih baru.**

Teks lisensi lengkap tersedia dalam **LICENSE**. Pertahankan pemberitahuan hak cipta dan lisensi dari setiap komponen yang digunakan.

## Rujukan

- [Pedoman publikasi plugin QGIS](https://plugins.qgis.org/docs/publish)
- [Struktur dan pelepasan plugin QGIS](https://docs.qgis.org/4.2/en/docs/pyqgis_developer_cookbook/plugins/releasing.html)
- [Pengelolaan plugin dan pemasangan ZIP](https://docs.qgis.org/4.2/en/docs/user_manual/plugins/plugins.html)
- [Teks resmi GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.html)

