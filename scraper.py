'''
Script untuk melakukan scraping data akreditasi program studi dari website BANPT
menggunakan Selenium untuk menangani DataTables yang menggunakan AJAX loading.
'''
import csv
import time
import json
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException, WebDriverException

from bs4 import BeautifulSoup

# Common User-Agent string to mimic a real browser
COMMON_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"

def setup_driver(webdriver_executable_path, headless=False):
    '''Inisialisasi Selenium WebDriver.'''
    try:
        # Setup Chrome options
        options = webdriver.ChromeOptions()
        options.add_argument(f"user-agent={COMMON_USER_AGENT}")
        options.add_argument("--start-maximized")
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        if headless:
            options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=2560,1440")  # Ukuran layar yang lebih besar
        options.add_argument("--force-device-scale-factor=0.5")  # Zoom out 50%
        
        # Initialize WebDriver
        if webdriver_executable_path and webdriver_executable_path.strip():
            driver = webdriver.Chrome(executable_path=webdriver_executable_path, options=options)
        else:
            print("Path WebDriver tidak disediakan, mencoba mencari di PATH sistem...")
            driver = webdriver.Chrome(options=options)
        
        print("ChromeDriver berhasil diinisialisasi.")
        return driver
    except Exception as e:
        print(f"Error saat inisialisasi ChromeDriver: {e}")
        print("Pastikan ChromeDriver sudah terinstal dan path-nya benar atau ada di PATH sistem.")
        return None

def wait_for_table_data(driver, max_retries=3):
    '''Menunggu data tabel dimuat dan retry jika perlu.'''
    wait = WebDriverWait(driver, 20)
    
    for attempt in range(max_retries):
        try:
            print(f"    Percobaan {attempt + 1}: Menunggu tabel data dimuat...")
            
            # Tunggu tabel muncul
            table = wait.until(EC.presence_of_element_located((By.ID, "table")))
            
            # Tunggu sebentar agar AJAX selesai loading
            time.sleep(3)
            
            # Cek apakah ada data di dalam tbody
            tbody = table.find_element(By.TAG_NAME, "tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            
            if len(rows) > 0 and "No data available in table" not in tbody.text:
                print(f"    Berhasil! Ditemukan {len(rows)} baris data.")
                return True
            else:
                print(f"    Percobaan {attempt + 1}: Tabel kosong atau belum dimuat. Refresh halaman...")
                driver.refresh()
                time.sleep(5)
                
        except Exception as e:
            print(f"    Percobaan {attempt + 1} gagal: {e}")
            if attempt < max_retries - 1:
                driver.refresh()
                time.sleep(5)
    
    print("    Gagal memuat data tabel setelah beberapa percobaan.")
    return False

def set_table_entries_to_100(driver):
    '''Mengatur dropdown jumlah entries ke 100.'''
    try:
        wait = WebDriverWait(driver, 10)
        
        # Cari dropdown untuk entries
        entries_select = wait.until(EC.element_to_be_clickable((By.NAME, "table_length")))
        
        # Pilih 100 entries
        select = Select(entries_select)
        select.select_by_value("100")
        
        print("    Berhasil mengatur jumlah entries ke 100.")
        
        # Tunggu tabel di-update
        time.sleep(3)
        return True
        
    except Exception as e:
        print(f"    Error saat mengatur entries: {e}")
        return False

def extract_table_data(driver):
    '''Mengekstrak data dari tabel yang sedang dimuat.'''
    try:
        table = driver.find_element(By.ID, "table")
        tbody = table.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")
        
        print(f"    Mengekstrak data dari {len(rows)} baris...")
        
        extracted_data = []
        
        # Verifikasi struktur header tabel
        try:
            thead = table.find_element(By.TAG_NAME, "thead")
            header_cells = thead.find_elements(By.TAG_NAME, "th")
            print(f"    Tabel memiliki {len(header_cells)} kolom header")
        except Exception as e:
            print(f"    Warning: Gagal mengakses header tabel: {e}")
        
        for i, row in enumerate(rows):
            # Cari semua td dan juga yang mungkin tersembunyi
            cells = row.find_elements(By.TAG_NAME, "td")
            
            # Progress indicator setiap 25 baris
            if i > 0 and i % 25 == 0:
                print(f"    Progress: {i} baris diproses...")
            
            if len(cells) >= 7:  # Minimal 7 kolom (untuk memastikan ada kolom peringkat)
                # Cek apakah baris kosong atau loading
                if "No data available" in row.text or "Loading" in row.text:
                    continue
                
                # Ekstrak menggunakan JavaScript untuk mendapatkan semua kolom termasuk yang tersembunyi
                try:
                    all_cell_texts = driver.execute_script("""
                        var row = arguments[0];
                        
                        // Coba ambil dari DataTables API jika memungkinkan
                        var table = $('#table').DataTable();
                        var rowData = table.row(row).data();
                        
                        if (rowData && rowData.length >= 8) {
                            // Jika DataTables API berhasil, gunakan data dari sana
                            return rowData;
                        }
                        
                        // Fallback: ambil semua td termasuk yang tersembunyi
                        var allCells = row.querySelectorAll('td');
                        var texts = [];
                        
                        // Paksa tampilkan semua kolom sementara
                        var originalStyles = [];
                        for(var i = 0; i < allCells.length; i++) {
                            originalStyles[i] = {
                                display: allCells[i].style.display,
                                visibility: allCells[i].style.visibility
                            };
                            allCells[i].style.display = 'table-cell';
                            allCells[i].style.visibility = 'visible';
                        }
                        
                        // Ambil text dari semua kolom
                        for(var i = 0; i < allCells.length; i++) {
                            texts.push(allCells[i].textContent.trim());
                        }
                        
                        // Kembalikan style asli
                        for(var i = 0; i < allCells.length; i++) {
                            allCells[i].style.display = originalStyles[i].display;
                            allCells[i].style.visibility = originalStyles[i].visibility;
                        }
                        
                        // Jika masih kurang dari 8 kolom, coba akses data dari atribut data-*
                        if (texts.length < 8) {
                            // Coba akses data dari atribut HTML yang mungkin ada
                            var dataAttrs = [];
                            for(var attr of row.attributes) {
                                if(attr.name.startsWith('data-')) {
                                    dataAttrs.push(attr.value);
                                }
                            }
                            texts = texts.concat(dataAttrs);
                        }
                        
                        return texts;
                    """, row)
                    
                    # Berdasarkan analisis HTML, tabel memiliki 8 kolom data
                    # Kolom ke-9 (Status Kedaluwarsa) adalah hasil render JavaScript DataTables
                    
                    # Mapping berdasarkan 8 kolom aktual + 1 kolom yang di-render JavaScript
                    row_data = {
                        'perguruan_tinggi': all_cell_texts[0] if len(all_cell_texts) > 0 else "",
                        'program_studi': all_cell_texts[1] if len(all_cell_texts) > 1 else "",
                        'strata': all_cell_texts[2] if len(all_cell_texts) > 2 else "",
                        'wilayah': all_cell_texts[3] if len(all_cell_texts) > 3 else "",
                        'no_sk': all_cell_texts[4] if len(all_cell_texts) > 4 else "",
                        'tahun_sk': all_cell_texts[5] if len(all_cell_texts) > 5 else "",
                        'peringkat': all_cell_texts[6] if len(all_cell_texts) > 6 else "",
                        'tanggal_kedaluwarsa': all_cell_texts[7] if len(all_cell_texts) > 7 else "",
                        'status_kedaluwarsa': "",  # Akan diisi dari kolom computed jika ada
                        'scraped_at': datetime.now().isoformat()
                    }
                    
                    # Coba ambil status kedaluwarsa dari kolom yang di-render JavaScript (jika ada)
                    if len(all_cell_texts) > 8:
                        row_data['status_kedaluwarsa'] = all_cell_texts[8]
                    
                    # Konfirmasi ekstraksi data pertama
                    if len(extracted_data) == 0 and row_data['perguruan_tinggi']:
                        print(f"    Berhasil mengekstrak data. Contoh: {row_data['perguruan_tinggi']} - {row_data['program_studi']}")
                    
                except Exception as e:
                    print(f"    Warning: Gagal ekstrak dengan JavaScript: {e}, fallback ke metode biasa")
                    # Fallback ke metode biasa jika JavaScript gagal
                    row_data = {
                        'perguruan_tinggi': cells[0].text.strip() if len(cells) > 0 else "",
                        'program_studi': cells[1].text.strip() if len(cells) > 1 else "",
                        'strata': cells[2].text.strip() if len(cells) > 2 else "",
                        'wilayah': cells[3].text.strip() if len(cells) > 3 else "",
                        'no_sk': cells[4].text.strip() if len(cells) > 4 else "",
                        'tahun_sk': cells[5].text.strip() if len(cells) > 5 else "",
                        'peringkat': cells[6].text.strip() if len(cells) > 6 else "",
                        'tanggal_kedaluwarsa': cells[7].text.strip() if len(cells) > 7 else "",
                        'status_kedaluwarsa': cells[8].text.strip() if len(cells) > 8 else "",  # Coba ambil jika ada
                        'scraped_at': datetime.now().isoformat()
                    }
                
                # Skip baris jika data utama kosong
                if not any([row_data['perguruan_tinggi'], row_data['program_studi']]):
                    continue
                
                extracted_data.append(row_data)
        
        print(f"    Berhasil mengekstrak {len(extracted_data)} data dari {len(rows)} baris")
        return extracted_data
        
    except Exception as e:
        print(f"    Error saat ekstraksi data: {e}")
        return []

def get_total_pages(driver):
    '''Mendapatkan jumlah total halaman.'''
    try:
        # Cari info pagination
        pagination_info = driver.find_element(By.ID, "table_info").text
        # Format: "Showing 1 to 100 of 21,034 entries (filtered from 33,552 total entries)"
        
        # Extract total entries
        if "entries" in pagination_info:
            parts = pagination_info.split()
            for i, part in enumerate(parts):
                if part == "of":
                    total_entries_str = parts[i + 1].replace(",", "")
                    total_entries = int(total_entries_str)
                    # Asumsi 100 entries per halaman
                    total_pages = (total_entries + 99) // 100  # Ceiling division
                    print(f"    Total entries: {total_entries}, Total halaman: {total_pages}")
                    return total_pages
        
        return 1
        
    except Exception as e:
        print(f"    Error mendapatkan info pagination: {e}")
        return 1

def go_to_next_page(driver):
    '''Navigasi ke halaman berikutnya.'''
    try:
        wait = WebDriverWait(driver, 10)
        
        # Coba beberapa selector untuk tombol Next
        next_selectors = [
            "#table_next a",  # Link di dalam tombol Next
            "#table_next",    # Tombol Next itu sendiri 
            ".paginate_button.next a",  # Selector alternatif
            "a[data-dt-idx]:contains('Next')",  # Berdasarkan text
        ]
        
        next_button = None
        for selector in next_selectors:
            try:
                if selector.startswith("#"):
                    next_button = driver.find_element(By.CSS_SELECTOR, selector)
                else:
                    next_button = driver.find_element(By.CSS_SELECTOR, selector)
                
                if next_button and next_button.is_displayed():
                    break
            except:
                continue
        
        if not next_button:
            print("    Error: Tombol Next tidak ditemukan")
            return False
        
        # Cek apakah tombol Next aktif (tidak disabled)
        parent_li = next_button.find_element(By.XPATH, "./ancestor::li[1]")
        if "disabled" in parent_li.get_attribute("class"):
            print("    Sudah di halaman terakhir.")
            return False
        
        # Scroll ke tombol jika perlu
        driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
        time.sleep(1)
        
        # Klik tombol Next menggunakan JavaScript sebagai fallback
        try:
            next_button.click()
        except:
            print("    Menggunakan JavaScript click sebagai fallback...")
            driver.execute_script("arguments[0].click();", next_button)
        
        print("    Navigasi ke halaman berikutnya...")
        
        # Tunggu tabel di-update dengan indikator loading
        time.sleep(3)
        
        return True
        
    except Exception as e:
        print(f"    Error navigasi ke halaman berikutnya: {e}")
        return False

def scrape_banpt_prodi_directory(driver, max_pages=None):
    '''Scraping utama untuk direktori program studi BANPT.'''
    banpt_url = "https://www.banpt.or.id/direktori/prodi/pencarian_prodi.php"
    all_data = []
    
    try:
        print(f"Navigasi ke: {banpt_url}")
        driver.get(banpt_url)
        
        # Maksimalkan window dan atur zoom untuk memastikan semua kolom terlihat
        driver.maximize_window()
        time.sleep(2)
        
        # Set zoom level ke 50% menggunakan JavaScript
        try:
            driver.execute_script("""
                // Method 1: Document zoom
                document.body.style.zoom = '0.5';
                
                // Method 2: CSS transform (fallback)
                document.body.style.transform = 'scale(0.5)';
                document.body.style.transformOrigin = 'top left';
                
                // Method 3: Viewport manipulation
                var viewportMeta = document.querySelector('meta[name="viewport"]');
                if (viewportMeta) {
                    viewportMeta.setAttribute('content', 'width=2560, initial-scale=0.5');
                } else {
                    var meta = document.createElement('meta');
                    meta.name = 'viewport';
                    meta.content = 'width=2560, initial-scale=0.5';
                    document.head.appendChild(meta);
                }
            """)
            print("    Mengatur zoom ke 50% untuk menampilkan semua kolom...")
            time.sleep(3)
        except Exception as e:
            print(f"    Warning: Gagal mengatur zoom: {e}")
        
        # Tunggu dan pastikan data tabel dimuat
        if not wait_for_table_data(driver):
            print("Gagal memuat data tabel.")
            return all_data
        
        # Set jumlah entries ke 100
        if not set_table_entries_to_100(driver):
            print("Gagal mengatur entries, melanjutkan dengan setting default.")
        
        # Coba disable responsive untuk memastikan semua kolom tampil
        try:
            driver.execute_script("""
                // Manipulasi CSS untuk memaksa semua kolom tampil
                $('head').append('<style type="text/css">' +
                    '#table { width: auto !important; table-layout: auto !important; }' +
                    '#table td, #table th { display: table-cell !important; visibility: visible !important; }' +
                    '.dtr-hidden { display: table-cell !important; }' +
                    '@media screen { #table td, #table th { display: table-cell !important; } }' +
                    '</style>');
                
                // Coba disable responsive DataTables
                if (typeof $.fn.dataTable !== 'undefined') {
                    var table = $('#table').DataTable();
                    if (table.responsive) {
                        table.responsive.disable();
                        table.columns.adjust().draw();
                    }
                }
                
                // Paksa tampilkan semua kolom yang mungkin tersembunyi
                $('#table td, #table th').each(function() {
                    $(this).show();
                    $(this).css({
                        'display': 'table-cell',
                        'visibility': 'visible'
                    });
                    $(this).removeClass('dtr-hidden');
                });
                
                // Trigger window resize untuk memaksa recalculation
                $(window).trigger('resize');
            """)
            print("    Mematikan responsive dan memaksa semua kolom tampil...")
            time.sleep(3)
        except Exception as e:
            print(f"    Warning: Gagal manipulasi responsive: {e}")
        
        # Tunggu data dimuat ulang setelah perubahan entries
        time.sleep(5)
        if not wait_for_table_data(driver, max_retries=2):
            print("Gagal memuat ulang data tabel setelah mengatur entries.")
            return all_data
        
        # Dapatkan total halaman
        total_pages = get_total_pages(driver)
        if max_pages:
            total_pages = min(total_pages, max_pages)
        
        # Estimasi waktu (asumsi 5 detik per halaman)
        estimated_time = total_pages * 5
        estimated_minutes = estimated_time // 60
        print(f"    Estimasi waktu scraping: ~{estimated_minutes} menit ({estimated_time} detik)")
        
        current_page = 1
        
        while current_page <= total_pages:
            print(f"\n  Scraping halaman {current_page} dari {total_pages} ({len(all_data)} data terkumpul)...")
            
            # Ekstrak data dari halaman saat ini
            page_data = extract_table_data(driver)
            
            if page_data:
                all_data.extend(page_data)
                print(f"    +{len(page_data)} data dari halaman {current_page}")
            else:
                print(f"    Tidak ada data yang diekstrak dari halaman {current_page}")
            
            # Jika sudah halaman terakhir atau mencapai max_pages, stop
            if current_page >= total_pages:
                break
                
            # Navigasi ke halaman berikutnya
            if not go_to_next_page(driver):
                print("    Tidak bisa melanjutkan ke halaman berikutnya.")
                break
            
            current_page += 1
            
            # Delay antar halaman
            time.sleep(2)
        
    except Exception as e:
        print(f"Error dalam scraping utama: {e}")
    
    return all_data

def save_to_csv(data_list, csv_file_path):
    '''Menyimpan data ke file CSV.'''
    if not data_list:
        print("Tidak ada data untuk disimpan ke CSV.")
        return
        
    try:
        fieldnames = data_list[0].keys()
        
        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data_list)
            
        print(f"💾 Data berhasil disimpan ke '{csv_file_path}'")
        
    except IOError:
        print(f"Error: Tidak dapat menulis ke file CSV '{csv_file_path}'.")
    except Exception as e:
        print(f"Error saat menyimpan ke CSV: {e}")

if __name__ == '__main__':
    # --- KONFIGURASI SCRAPING ---
    WEBDRIVER_PATH = ""  # Kosongkan jika ChromeDriver ada di PATH
    RUN_HEADLESS = False  # Set ke True untuk menjalankan tanpa UI
    MAX_PAGES = None  # Set ke angka untuk membatasi jumlah halaman, None untuk semua
    DELAY_BETWEEN_OPERATIONS = 2  # Jeda antar operasi (detik)
    CSV_OUTPUT_FILENAME = "banpt_akreditasi_prodi.csv"
    # --- AKHIR KONFIGURASI ---

    print("Memulai scraping data akreditasi program studi BANPT...")
    
    # Setup WebDriver
    driver = setup_driver(WEBDRIVER_PATH, headless=RUN_HEADLESS)
    if not driver:
        print("Gagal setup WebDriver. Program berhenti.")
        exit()

    try:
        # Lakukan scraping
        scraped_data = scrape_banpt_prodi_directory(driver, max_pages=MAX_PAGES)
        
        if scraped_data:
            print(f"\n🎉 SCRAPING SELESAI!")
            print(f"📊 Total {len(scraped_data)} data akreditasi program studi berhasil diekstrak")
            save_to_csv(scraped_data, CSV_OUTPUT_FILENAME)
        else:
            print("\n❌ Tidak ada data yang berhasil diekstrak.")
            
    finally:
        if driver:
            print("\nMenutup WebDriver...")
            driver.quit()
            print("WebDriver berhasil ditutup.")

    print("Proses scraping selesai.")