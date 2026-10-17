# 17 Ekim 2026 fiziksel kayıt incelemesi

Oturum: `dec3042495ca4ab78b58b947e2b3c73a`; çalışan HEAD: `32a8e14991e6d1d308909602084ab2e1f7b7d815`.
Yerel saat: 13:47:51–13:56:35. 2.844 sıralı olay; kayıp, yazma hatası ve dosya döndürme yok.

53 başlatma denemesi: 15'i başlangıçta reddedildi, 38'i terminal sonuç üretti.
Terminal sonuçlar: 7 INCONCLUSIVE, 20 BLOCKED, 5 kullanıcı iptali ABORTED, 2 otomatik PASSED, 4 PASSED_USER (3 farklı hedef).

| Kapsam | Kanıt / sonuç |
|---|---|
| H01 extruder, run 1 | Hedef 60°C, test tavanı 70°C, ölçüm 70,37°C, güç 0. Güvenlik shutdown'u; restore doğrulanmadı. Tavan kaldırılmaz. |
| Sonraki 15 H denemesi | `thermal_busy_or_locked`; ısıtma komutu gönderilmedi. Bunlar bağımsız 15 termal arıza değildir. |
| M03/M04/M05/M06/M12, runs 17–27 | `motion_requires_cold_idle_heaters`; sıcak hotend nedeniyle komut öncesi BLOCKED. |
| M01 X/Y, runs 28/29 | Yanıt `stepper_x=open`, `stepper_y=open` iken kod yalnız x/y arıyordu. Kayıtla doğrulanmış parser hatası düzeltildi; fiziksel kabul hâlâ bekliyor. |
| M10, runs 30–33 | `driver_monitor_disabled_or_unknown`. Sağlıklı motor veya kesin sürücü arızası sonucu çıkarılamaz. Yeni kayıtta drv_status alanı da tutulur. |
| P01, runs 34/37 | Kullanıcı iptali. Run 34 boyunca “Release probe” aşaması ilerlemedi; neden için doğru fiziksel released/triggered/released denemesi gerekir. |
| P03, run 36 | Otomatik PASSED: range 0,0175 mm, stddev 0,005362 mm, 10 örnek. Mutlak doğruluk veya kullanıcı fiziksel kabulü değildir. |
| P04, run 40 | Otomatik PASSED: X/Y=117,5 mm, Z=-0,021667 mm. Önceki iki denemede Z yükseltme önkoşulu eksikti. |
| E03, run 41 | Yok→var gözlendi; son yok adımı onaylanmadan kullanıcı iptal etti. Sensör enabled=true restore kanıtı var. |
| E01/E02/E07 | Aktif extruder ön ısıtması eksik; komut öncesi BLOCKED. |
| E11 | MMU açık olduğundan önkoşul reddi. Önce normal menüden MMU disable gerekir. |
| E12, run 47 | Grip seçimi hazırlıkta ValueError; hareket gönderilmedi. Eski kayıt mesajı gizlediği için kesin MMU engeli bu dosyadan çıkarılamaz. Bilinen MMU hata metinleri sonraki kayıtta sabit güvenli kodlara çevrilir. |
| S15, run 48 | GPIO +2/-3/basma 1; açık observe(true); PASSED_USER, restore=true. Kabul edildi. |
| S16, run 50 | Beş renk adımı + açık observe(true); PASSED_USER, restore=true. Kabul edildi. Sonraki iptal edilmiş yeniden açış bu kabulü silmez. |
| S17, runs 51/53 | 10/50/100% + restore + açık observe(true); iki PASSED_USER. Kabul tek hedef için işlendi. |

## UI sonucu

1.976 UI olayı incelendi. Yakalanan `ui_handler_error` yok.
Bu oturumda `pulse → tests` doğrudan dönüşü yok; sonuç ekranı ve kullanıcı Back seçimi arada bulunuyor.
İlk H shutdown'undan sonra result → recovery → ana ekran geçişi var.
Bu kayıt tüm olası UI hatalarının bulunmadığını kanıtlamaz; önceki “listeye atıyor” sorununu bu oturumda yeniden üretmiyor.
Ekran satırlarındaki “ / ” işaretinin kayıt filtresinde gereksiz gizlendiği görüldü; aralıklı UI ayırıcıları korunacak, dosya yolu/URL gizleme sürecek.

## Yeniden test

- H güvenlik kilidini atlama. Donanım güvenli/OFF doğrulandıktan sonra yeni Petrel oturumu ile ilerle; H01 aşım nedenini ele almadan tavanı gevşetme.
- Önce soğuk testler; hotend soğukken M hareket grubu, home/Z şartları sağlanmışken P grubu.
- M01 düzeltmesinden sonra X/Y fiziksel released→pressed→released.
- E03'te son Remove filament adımında “read” seç; Cancel seçimi testi iptal eder.
- E11 için MMU disable; E01/E02/E07 için ayrı kararlı ön ısıtma.
- E12'yi yeni ayrıntılı kod ile yeniden kaydet.
- S15/S16/S17 kabulü tamamlandı; sadece yeni regresyon varsa tekrar gerekir.

[Kabul çizelgesi](maintenance-reference-printer-acceptance_TR.md) · [English](maintenance-acceptance-2026-10-17.md)
