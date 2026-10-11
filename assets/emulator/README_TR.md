# Emülatör kaynakları

[English](README.md) · [Türkçe](README_TR.md) · [Görüntü alma rehberi](../../docs/ui-emulator_TR.md)

## Eşleşen kaynakları seçme

Bu dosyalar Pi üzerinde ekran görüntüsü çiziminde kullanılır. Emülatörü açmak bunları fiziksel ekrana kurmaz veya ekranın font/ikonlarını değiştirmez.

| Dosya | Kullanım |
|---|---|
| `7.ICO` | 7 numaralı konumdaki uygulama ikon kütüphanesi; stok ikonlar ve 92/93 About çeşitleri |
| `0T5UIC1.HZK` | Varsayılan özgün T5UIC1 fontu |
| `0_DWIN_ASC.HZK` | Alternatif DGUS ASCII fontu; yalnız uygun olduğunda açıkça seçin |

Özel panel fontu için servis ortamında `DWIN_EMULATOR_FONT` değişkenine eşleşen dosyayı verip yeniden başlatın. [Ek emülatör ayarlarına](../../docs/ui-emulator_TR.md#ek-ayarlar) bakın. Ekran görüntüsüyle fiziksel ekranı karşılaştırırken kaynakların eşleşmesi önemlidir.

## Kaynak kökeni

- `0T5UIC1.HZK`: [Quint097/DWIN_Font_Tools](https://github.com/Quint097/DWIN_Font_Tools/blob/main/HZK%20Font%20Files/DWIN%20Font%20(Original)/0T5UIC1.HZK).
- `0_DWIN_ASC.HZK`: [ihrapsa/T5UIC1-DWIN-toolset](https://github.com/ihrapsa/T5UIC1-DWIN-toolset/blob/main/Dwin_Toolbox-en%2F0_DWIN_ASC.HZK).

Üst projelerin kaynak kökeni korunur; KlipperDWIN bu ikili dosyaların yazarlığını üstlenmez.
