# Maintenance filament ve MMU

[English](maintenance-filament.md)

E01/E07 bilinen aktif ekstrüder, min_extrude_temp üzerinde kararlı sıcaklık, can_extrude, açık yol ve homing ister. Onaylı SAVE/hareket/hareketsiz temizleme ile 1 mm/s hızda 5 mm komut eder; modal durum geri okunur. E02 10 mm komut eder, haricen ölçülmüş uzunluğu zorunlu tutar ve farkı gösterir; rotation_distance yazmaz.

E03 ENABLE=0 ile sensör takma/runout makrolarını bastırır; yok → var → yok geçişini ölçer ve başlangıç etkinlik durumunu geri yükler. E04 eşleşen ekstrüderle 5 mm besleme ve güncel false → true hareket bildirimi ister. Yeni geçiş olmadan kilitli true sinyali yeterli değildir; sensör bildirimi ölçülmüş besleme uzunluğu değildir. Belirsiz geri yükleme açıkça bildirilir.

E05 gerçek çapı okur. E06 zaman ve konfigürasyon kimliğiyle sınırlı açık yakalamaları kalıcı tutar; kesintisiz/ömür boyu izleme değildir. E08 gerçek on saniyelik yük hücresi örnekleri ve raporlanmış sensör hatası bulunmamasını ister. E09 tare, beyan edilmiş izlenebilir referans (50–25000 g), sayısal kalibrasyon sonucu ve eşleşen bekleyen konfigürasyon ister. SAVE_CONFIG gönderilmez.

E11/E12 **şimdilik Maintenance altında çalıştırılamaz ve menüde görünmez**. Önceki E11 akışı kullanıcıdan tüm MMU'yu elle kapatmasını ve sensörlere elle filament parçası takıp çıkarmasını istiyordu. Yeni tasarım kuralı: yalnız bir testi çalıştırmak için kullanıcıdan alt sistemi elle kapatması/açması istenmez. İleride E11 yeniden uygulanacaksa yalnız açık güvenlik kontrolleriyle MMU'nun önceki durumunu kaydedebilen, geçişi otomatik yapan, başarı/iptal/hata durumlarında **özgün durumu doğrulayarak geri yükleyen** bir işlem kullanılabilir. Bunlar garanti edilemiyorsa çalıştırılabilir test eklenmez. E12 de beklemeye alındı: eski grip/release/selector-home firmware okumaları ve tek kullanıcı onayı tam mekanik test kanıtı değildir. Donanım keşfi yeteneği raporlayabilir, fakat bu çalışma izni veya fiziksel kabul değildir. Eski BLOCKED kayıtları korunur.

İsteğe bağlı rol dosyası: ~/.config/Petrel/maintenance-filament.json, version 1. Desteklenen anahtarlar:
- dryers: object, target, ceiling, duration_s (30–21600 s) alanlarıyla en fazla dört açık cihaz; yalnız yapılandırılmış heater_generic, target < ceiling < max_temp ve 5–15 °C pay.
- chamber_sensor: yapılandırılmış nem sensörünün tam nesne adı.
- loadcell_reference: adı belirtilmiş izlenebilir referans/alet.
- material_history: en fazla on altı bağlantılı spool_id/material/used_mm/source kaydı.

E14 yalnız beyan edilmiş kurutucuyu, güncel termal kontroller ve OFF geri okumasıyla sınırlı bekletme parçalarında çalıştırır. İptal veya belirsiz aktif komut Klipper emergency_stop ister. Genel ısıtıcı kendiliğinden kurutucu sayılmaz. E13 gerçek Spoolman API kanıtı ister; beyan edilmiş bağlantılı kullanımı gösterir, aşınmayı ölçmez. E15 hazne nemini gösterir, filamentin iç nemini değil. İkisi INFORMATION tanılamasıdır.

Sonraki her eylem kuyruk/bağlantı kontrolünü yeniler. Kullanıcı sorularının süresi dolmaz. Firmware hatası hareketi tekrar göndermez. CI fiziksel kabul değildir.
