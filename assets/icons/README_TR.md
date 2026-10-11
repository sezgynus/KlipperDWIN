# Yönetilen LCD ikonları

[English](README.md) · [Türkçe](README_TR.md)

Baseline JPEG dosyalarını buraya ekleyin veya mevcut olanları değiştirin. Dosya adı ikon ID'siyle başlamalı: `092.jpg`, `092-about.jpg` veya `092_about.jpeg`. ID aralığı 0–255'tir; her ID yalnız bir dosyada kullanılabilir. Mevcut ID'lerin anlamı korunur. ID ve içerik aynı kalırken dosya adını değiştirmek yükleme başlatmaz. Yeni görsel kütüphaneye girer; ID'nin arayüzde nerede gösterileceğini UI kodu seçer.

JPEG'ler boyutlandırılmadan ve yeniden sıkıştırılmadan korunur. Progressive JPEG, yinelenen ID ve 32767 bayttan büyük görseller reddedilir. Kütüphane Picture Flash 7–15 slotlarına sığmalıdır; stok 0–2 resimleri ve 5/6 atlasları korunur.

Uygulama güncellemesinden sonraki ilk LCD bağlantısında bu klasörden kütüphane oluşturulur. Paketleyici büyük ikonları önce yerleştirir ve küçük ikonlarla kalan boşlukları doldurur. ID sırası fiziksel yerleşimden bağımsızdır. Her bloğun son baytı ayrılır ve UART yazımına dahil edilmez. Hiçbir JPEG blok sınırını geçmez.

Yalnız değişen bloklar yüklenir; tablo bloğu en son yazılır. Paneldeki kayıt tamamlanan blokları saklar; sonraki açılış eksik yüklemeyi tamamlar. Değişmeyen kütüphanede Flash yazılmaz. Başarısız Picture Flash denemesi aynı süreçte tekrarlanmaz. Yükleme ilerlemesi ve hatalar loglarda yer alır.

Çalışma sırasında kullanılan paketin aynısını dışa aktarın:

```bash
python tools/pack_icon_library.py assets/icons /tmp/7.ICO
```

Emülatör de bu JPEG kaynaklarını kullanır. `assets/emulator/7.ICO` referans çıktıdır; otomatik güncellemenin kaynağı değildir.

Panel kaynaklarını yeniden yüklediğinizde, kayıt eski kurulumu tarif ediyor olabileceğinden zorla yeniden yükleyin:

```bash
sudo systemctl stop KlipperDWIN.service
~/klipperdwin-env/bin/python ~/KlipperDWIN/tools/reload_icons.py
sudo systemctl start KlipperDWIN.service
```

Yazma onayları ve kayıt geri okuması doğrulanır; Picture Flash'ın kendisi geri okunmaz. Yeni ikon yerleşimini fiziksel ekranda kontrol edin.
