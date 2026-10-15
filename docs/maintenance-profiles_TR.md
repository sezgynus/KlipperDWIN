# Maintenance aktüatör açık izin profilleri

[English](maintenance-profiles.md)

Aşama 8 öz testi ancak üç bağımsız şart karşılandığında aktüatöre izin verir: **kullanıcının açık kaydı**, **gerçek Klipper keşfi** ve **güvenilir efektif ayarlar ile başlangıç durumu okuması**. Klipper'ın `fan` nesnesi özel part-cooling anlamına sahip olduğundan F01 için ek profile gerek yoktur. Rastgele `output_pin`'in case light veya buzzer olduğu varsayılmaz.

İsteğe bağlı Petrel case-light testi veya takılı buzzer'ı bilinçli olarak açmak için Pi'de Petrel servis kullanıcısıyla şu küçük dosyayı oluştur:

`~/.config/Petrel/maintenance-test-profiles.json`

```json
{
  "version": 1,
  "case_light": true,
  "buzzer_output": "tick",
  "fan_generic_output": "",
  "led_output": ""
}
```

`tick` yerine gerçekten yapılandırılmış `[pwm_cycle_time tick]` bölümündeki çıkış ismini yaz. Testi kapatmak için `case_light` değerini false, `buzzer_output` alanını boş metin yap. **Donanımın birebir eşleşmiyorsa örneği olduğu gibi uygulama.** Profiller yalnız sonraki Klipper READY epoch'unda/servis yeniden başlatmada okunur. Dosya okumak GPIO veya G-code çalıştırmaz.

Case light olarak yalnız PWM açık, scale 1 ayarlı `[output_pin case_light]` doğrulanabilir. Buzzer için yalnız başlangıç/shutdown değeri 0, geçerli scale bulunan ve açıkça kayıtlı `[pwm_cycle_time <output>]` bölümü doğrulanabilir. Komut yürütücüsü yine de canlı OFF durumunu ve geri yüklemeyi kanıtlamalı ve her test için ayrı kullanıcı onayı almalıdır. Hatalı, eksik veya büyük profiller hiçbir yetki sağlamaz. Fiziksel test otomatik başlamaz. CI yalnız simülasyon kanıtı sağlar, donanım PASS değildir.

Generic fan ve LED uyarımı da **açık izin** gerektirir. Bilinen manuel fan için `fan_generic_output` alanına `[fan_generic isim]` bölümündeki güvenli ismi, LED için `led_output` alanına tam nesne adını (ör. `neopixel board`) yaz. Çoklu LED pikselleri veya orijinal rengi bilinmeyen cihazlar komut derleyicisinde daima engellenir. Gerekmeyen alanları boş bırak.
