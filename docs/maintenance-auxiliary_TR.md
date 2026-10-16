# Maintenance yardımcı donanım

[English](maintenance-auxiliary.md)

O03/O04 mevcut açık izinli ışık/çıkış ve LED yürütücülerini korur. Rastgele çıkış, bilinmeyen makro veya bulunmayan-MMU sahte testi eklenmez.

O01 tam kayıtlı gcode_button ve zararsız boş/yalnız mesaj eylemi ister. Profil butonu adlandırsa bile bilinmeyen makro, hareket komutu ve Jinja eylemleri reddedilir. Test güncel firmware durumundan RELEASED → PRESSED → RELEASED okur; butonun G-code'unu çalıştırmaz.

O02 açık güvenli servo aralığı ve firmware limitleri içinde 2–5 test açısı ister. Başlangıçtaki sıfır olmayan raporlanan PWM bu aralığa karşılık gelmelidir; enerjisiz servonun mekanik konumu bilinmez ve güvenli varsayılamaz. Her açı ayrı kullanıcı eylemi ister. Son açıdan sonra önceki darbe genişliği geri yüklenip okunur, ardından kullanıcı gözlemi alınır. Bu, raporlanan PWM ve kaba gözlenmiş hareketi doğrular; ölçülmüş açı/tork değildir. Belirsiz aktif iptal, doğrulanmamış ters hareket yerine Klipper emergency_stop kullanır.

O05 yalnız beyan edilmiş ortam sensörünü okur; hotend doğruluğunu kanıtlamaz. O06 beyan edilmiş fiziksel bakım adımlarını açık onaylarla gösterir; ölçülmüş parça sağlığı yerine kullanıcının yaptığı bakımı kaydeder. Soğuk boşta ısıtıcılar ve kapalı motorlar gerekir. Kullanıcı sorularının süresi dolmaz.

Roller ~/.config/Petrel/maintenance-auxiliary.json içinde beyan edilir:
```json
{
  "version": 1,
  "buttons": ["gcode_button service"],
  "servos": [{"object":"servo hatch","minimum_angle":30,"maximum_angle":150,"angles":[60,120]}],
  "ambient_sensor": "temperature_sensor room",
  "tasks": [{"id":"inspect_belt","label":"Inspect belt","steps":["Inspect for wear","Check fasteners"]}]
}
```
Bunlar örnektir; yazıcıya özel varsayılan değildir. Bütün fiziksel servo yolunu ve gerçek bakım talimatlarını kendi makineniz için inceleyin. Güvenli beyanlar firmware limitlerinin yerini almaz veya rastgele makro çalıştırma yetkisi vermez. Değişiklikler sonraki Klipper READY epoch'unda keşfedilir. Fiziksel kabul ertelenmiş durumdadır.
