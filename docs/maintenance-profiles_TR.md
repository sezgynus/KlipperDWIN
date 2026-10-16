# Maintenance: genel aktüatör rol profilleri

[English](maintenance-profiles.md)

Maintenance, bir Klipper GPIO'suna ne bağlandığını **isimden tahmin etmez**. Standart `fan` nesnesinin Klipper tarafından tanımlanan işlevi vardır; diğer fiziksel çıkışların rolü açıkça kullanıcı tarafından belirtilir. Cihaz adı, pin, cihaz sayısı ve rol eşleştirmesi Petrel kaynak kodundan değil, çalışan yazıcıdan ve kullanıcı profilinden gelir.

Petrel servis kullanıcısıyla `~/.config/Petrel/maintenance-test-profiles.json` dosyasını oluştur. **Sürüm 2** biçimi:

```json
{
  "version": 2,
  "actuators": [
    {"object": "output_pin enclosure", "role": "visual"},
    {"object": "output_pin tool_lamp", "role": "visual"},
    {"object": "pwm_cycle_time Alarm", "role": "audible"},
    {"object": "fan_generic aux", "role": "fan"},
    {"object": "neopixel board", "role": "led"}
  ]
}
```

Bunlar **örnek isimlerdir**, Petrel varsayılanları değildir. Gerçek Klipper nesne adlarınla değiştir; kullanılmayanları kaldır. Rol, kullanıcının fiziksel işlev beyanıdır; sensörle kanıtlanmış cihaz türü değildir. Profil yalnız bir sonraki Klipper READY döneminde (örneğin yazıcı boşta iken Petrel servisi yeniden başlatılınca) okunur. Maintenance menüsüne girmek G-code veya yeniden keşif başlatmaz.

| Rol | Gerekli Klipper nesnesi ve şartlar | Test |
| --- | --- | --- |
| `visual` | Adlandırılmış `output_pin`; PWM, `scale=1`, fiziksel pin ve canlı başlangıç değeri | O03 görsel değişim ve geri yükleme |
| `audible` | Adlandırılmış `pwm_cycle_time`; pin, geçerli sonlu scale, açıkça sıfır `value` ve `shutdown_value` | S18 kısa ses, OFF denemesi ve **insanın** sesin çıkıp durduğunu gözlemesi |
| `fan` | Mevcut `fan_generic` ve canlı başlangıç değeri | F04 kısa fan darbesi |
| `led` | Mevcut `led` / `neopixel` / `dotstar` / `pca9632`, geri yüklenebilir tek LED | O04 LED testi |

En fazla **16** kayıt ve **2048 bayt** kabul edilir. Bilinmeyen anahtar/rol, tekrar eden cihaz, tehlikeli nesne adı, eksik cihaz, güvensiz ayar ve geçersiz dosya ek yetki oluşturmaz. Eksik ama geçerli tanımlanmış tekil cihazlar devre dışı kalır. Eski **sürüm 1 bilerek güvenli biçimde reddedilir**; testten önce sürüm 2'ye taşı. Eski `case_light: true` yerine `{"object":"output_pin <gerçek_ad>","role":"visual"}`, `buzzer_output: "<ad>"` yerine `{"object":"pwm_cycle_time <gerçek_ad>","role":"audible"}` kullan. Eski `fan_generic_output` ve `led_output` alanları, tam Klipper nesne adlarını içeren `fan` ve `led` kayıtlarına dönüşür.

S18 artık tek bir global buzzer işareti değil, **cihaz başına** testtir; birden fazla sesli çıkış ayrı listelenir. `pwm_cycle_time` çoğunlukla `printer.objects.list` içinde yoktur; açıkça onaylı efektif ayarlar yapısal kanıt sağlar. `SET_PIN PIN=...` komutundaki büyük/küçük harfe duyarlı özgün isim, salt-okunur ön kontrolde Klipper'ın ham yapılandırmasından çözülür ve pin efektif ayarla karşılaştırılır. O03 de aynı ad doğrulamasını yapar ve komuttan önce canlı başlangıç değeri ister. Ses çıkışında hayalî durum geri okuması kullanılmaz. Duyulan ses `OBSERVED_USER` ve `restore_verified=False` olur; telemetriyle geri yüklemenin kanıtı sayılmaz.

**Güvenlik:** Profil, keşif veya menüye giriş sırasında otomatik G-code gönderme izni değildir. Her fiziksel testte yazıcının boşta/kuyruğun güvenli olması, ikinci açık onay ve sınırlı komut gönderimi gerekir. Başlangıç durumu veya ham pin kanıtı eksikse çalışma engellenir. İsimde `light` ya da `buzzer` sözcüğü geçmesi tek başına hiçbir testi başlatmaz. GitHub CI taklit veriler kullanır, fiziksel kabul anlamına gelmez.

**O04 çoklu LED notu:** `led` rolü, 1–32 adet aynı tip RGB veya RGBW pikselli indeksli zincirler dâhil gerçek Klipper LED nesnesini seçer. Her pikselin tam başlangıç rengi okunmalı ve kendisine özel renk geri yüklenmelidir. MMU/efekt tarafından yönetilen zincirlerde bu rol **tek başına yeterli değildir**: `mmu_leds` veya LED efekt yapılandırması zincirin kontrolünü elinde tutuyorsa fiziksel O04 ön kontrolde engellenir. Ayrı bir güvenli kontrol devri uygulanmadan profil sahipliği devretmez ve animasyon durdurmaz.
