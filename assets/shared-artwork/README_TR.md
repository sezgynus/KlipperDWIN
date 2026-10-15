# Ortak resim kaynakları

[English](README.md) · [Türkçe](README_TR.md) · [LCD görselleri](../README_TR.md#ortak-ui-görsel-sayfası)

Her kaynak görseli buraya `.jpg` veya `.jpeg` olarak koyun. Repo kökünden çalıştırın:

```bash
python tools/pack_shared_artwork.py
```

Araç hem `assets/petrel_shared.jpg` (Picture Flash slot 1) hem `shared_artwork_layout.py` dosyasını üretir. Kaynak JPEG'leri ve iki üretilen dosyayı birlikte commit edin. Üretim geliştiricinin çalıştırdığı bir işlemdir; kullanıcıya hazır çıktılar gelir ve servis değişen görseli otomatik yükler.

| Kaynak dosya adı | Üretilen dikdörtgen | Üretilen boyutlar |
|---|---|---|
| `qr.jpg` | `QR_BOX` | `QR_SIZE` |
| `nozzle-idle.jpeg` | `NOZZLE_IDLE_BOX` | `NOZZLE_IDLE_SIZE` |

İsimler büyük harfli Python tanımlayıcılarına dönüştürülür; noktalama alt çizgi olur, aksanlar sadeleştirilir ve rakamla başlayan adlara `IMAGE_` eklenir. Dönüşüm sonrası birbiriyle veya üretilen metadata isimleriyle çakışan adlar reddedilir. `qr.jpg` dosyasını koruyun: Info onun `QR_BOX` tanımını kullanır. QR kaynağı marka görselinden `python tools/render_project_qr.py` ile yeniden üretilebilir; ardından paketleyiciyi çalıştırın. Paketleme tek başına hiçbir kaynak dosyasını değiştirmez.

Dikdörtgenler **portre** koordinatlarında `(sol, üst, sağ, alt)` biçimindedir; sağ/alt sınırlar dahil değildir. Boyutlar `(genişlik, yükseklik)` biçimindedir. Sayısal koordinatları kopyalamak yerine sabitleri import edin. `copy_cache1` için LCD'nin dahil ettiği koordinatları elde etmek üzere sağ/alt değerlerden 1 çıkarın. Görsel eklemek onu sayfada kullanılabilir yapar; ne zaman ve nerede gösterileceğini yine UI kodu belirler.

Portre tuval **272×480**; JPEG çıktısı panel yönü 1 için **480×272** saklanır. Paketleyici farklı MaxRects sıraları, yerleşim genişlikleri ve seçim kurallarını deneyerek kaplanan dikdörtgeni en kompakt tutan sonucu seçer. Bu deterministik bir sezgisel yöntemdir; matematiksel optimum garantisi değildir. Kaynaklar küçültülmez veya döndürülmez. Kaynaklar değişince yerleşim değişebilir; bu nedenle daima üretilen sabitleri kullanın.

Kaynaklar geometrik olarak sığmalı ve son baseline 4:2:0 JPEG **32767 baytı** aşmamalıdır. Boş klasör, geçersiz görsel, çakışan isim, paketleme başarısızlığı ve sıkıştırılmış boyut taşması önceki çıktıları değiştirmez. JPEG kalitesi varsayılan olarak 100'dür; optimize Huffman kodlaması kullanılır. Gerekirse `--quality 94` açıkça daha düşük kalite seçer. Görsel değişikliklerinden sonra sonucu inceleyin ve QR okunabilirliğini fiziksel panelde doğrulayın.

Repodaki hazır çıktıları değiştirmeden incelemek için:

```bash
python tools/pack_shared_artwork.py --output /tmp/petrel-page.jpg --layout /tmp/petrel-layout.py
```

Üretilen modül JPEG'in SHA-256 değerini içerir. JPEG/yerleşim uyuşmazlığında servis panele yazmadan işlemi reddeder. Çıktı dosyası değiştirme hatasında çift geri alınır; üretilen dosyalar yine birlikte commit edilip dağıtılmalıdır.
