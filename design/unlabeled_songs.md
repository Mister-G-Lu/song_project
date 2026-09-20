# Unlabeled Songs — Release Year Status

**Overall coverage: 92.9%** (2150/2314 rated songs have release years)

## Resolved (150+ songs)

These were manually labeled from general knowledge, web searches, and the
MusicBrainz/iTunes enrichment pipeline. All added to `data/release_year_cache.json`.

### Well-Known Songs (Parser Failures Fixed)

| Artist | Song | Year | Parser Issue |
|--------|------|------|-------------|
| A-ha | Take on Me | 1985 | "A-ha" splits on hyphen → "A" / "ha" |
| Ne-Yo | So Sick | 2006 | "Ne-Yo" splits → "Ne" / "Yo" |
| Liszt (spelled "Listz") | Feux Follets | 1847 | Misspelling + transliteration |
| Yiruma (spelled "Yurima") | River Flows in You | 2001 | Misspelling |
| Chopin | Etude Op. 25 No. 5 | 1833 | Reversed parser output |
| Coolio | 1,2,3,4 (Sumpin' New) | 1996 | Numbers confuse parser |
| Two Steps From Hell | Heart of Courage | 2010 | Long artist name |
| Phoenix Legend | Fly Freely | 2005 | Misspelling + tab character |
| Dimash Kudaibergen | SOS d'un terrien en détresse | 2017 | Accent chars in song |
| YOASOBI | 夜に駆ける (Yoru ni Kakeru) | 2019 | Japanese in parens reversed |
| George Strait | You'll Be There | 1996 | — |
| Camila Cabello ft. Young Thug | Havana | 2017 | ft. in title |
| Celeste | walk on air | 2019 | — |
| Izzy Bizu | Faded | 2015 | — |
| Aitana, Nicki Nicole | Formentera | 2022 | — |
| Magdalena Bay | Chaeri | 2022 | Reversed parser ("by" format) |
| Novo Amor | Birthplace | 2019 | — |
| Yeat | out of my way | 2022 | — |
| Bach | Prelude in C Major | 1722 | Year in title |
| Metro Boomin | Not All Heroes Wear Capes | 2018 | Unparseable |
| Dove Cameron | What a girl is | 2017 | No separator |

### Newly Resolved (This Session)

| Artist | Song | Year | Notes |
|--------|------|------|-------|
| B.A.P | HONEYMOON | 2016 | K-pop, underscore separator |
| Thomas Stringfellow | Lemonade | 2019 | Reversed parser |
| Synapson | I Believe in | 2019 | Reversed parser |
| Biig Piig | 9 to 5 | 2019 | Reversed parser |
| Griffin Lewis | Pinkie's Brew | 2021 | Reversed parser |
| Phoenix Legend | Most Dazzling Folk Style | 2009 | Reversed parser |
| Giorgio Gaber | Conformista | 1969 | "IL" label in title |
| Lalo Schrifrin | The Architect's Building | 1975 | "by" format |
| Blues Creation | Atomb Bombs Away | 1971 | "by" format |
| 11 Acorn Lane | Story Time | 2019 | — |
| 96Neko | I'm still alive today | 2019 | — |
| halaCG | Signed and Sealed | 2020 | — |
| Jocat | Grab Your Friends | 2022 | VTuber |
| Tuesday and Carole | Move Mountains | 2018 | — |
| Valgur | Mascara de Nina | 2019 | — |
| Herman Gjeitanger | One Like Putin | 2022 | — |
| Chipmunks | You Spin Me Right Round | 2009 | Cover |
| bothneco | choco-mint flavor | 2021 | Vocaloid ft. Hatsune Miku |
| Kambido | Boy something | 2020 | — |
| Kambido | Don't Know | 2020 | — |
| Kambido | Pirate | 2020 | — |
| Terminte | Aspiration | 2020 | — |
| EMI//NOVA | set sail on a comet tail | 2021 | Dot separator |
| hagali | たゆたいのイーファ | 2021 | CJK song title |
| Marine Corp | Hymn | 1919 | — |
| It's the Most Wonderful Time of the Year | — | 1963 | Christmas classic |
| Fate/Zero | OP 1 | 2012 | Anime |
| LION BABE | Where Do We Go? | 2018 | Tab-separated |
| Skies Forever Blue | Toby Fox & Itoki Hana | 2024 | Deltarune |
| Gong Xi Gong Xi | — | 1945 | Chinese New Year classic |
| Arash | Man O To | 2005 | Iranian-Swedish pop |
| Scissor Seven | Opening | 2018 | Chinese anime |
| RED | What You Keep Alive | 2020 | — |
| WAKING FREE | feat. SynthV Solaria | 2023 | Synthesizer V vocaloid |
| 秋山黄色 | Caffeine | 2020 | J-rock, CJK artist |
| 三月のパンタシア | パステルレイン | 2019 | Sangatsu no Phantasia |
| 君色々移り / Changing to Your Colors | Mafumafu | 2020 | Vocaloid producer |
| Varnam | Viribhoni | 2019 | Indian classical |
| DAZBEE | イビツナコトバ | 2020 | Vocaloid |

### Anime/Game OSTs

| Artist | Song | Year | Source |
|--------|------|------|--------|
| Kokia | Fukurou | 2005 | J-pop |
| Kokia | Kirin | 2005 | J-pop |
| YOASOBI | Yoru ni Kakeru | 2019 | J-pop |
| TUYU | It's Raining After All | 2021 | Vocaloid rock duo |
| TUYU | I'm getting on the bus to the other world | 2021 | Vocaloid rock duo |
| Yorushika | That's Why I Gave Up on Music | 2019 | J-rock |
| Animenz | this is (not) the end | 2018 | Piano arranger |
| MALICE MIZER | 追憶の欠片 | 1998 | Visual kei |
| Ado | Kira (綺羅) | 2020 | J-pop |
| Ado | God-ish (神っぽいな) | 2021 | J-pop |
| Mai Kuraki | Kimi to Koi no mama de Owarenai | 2000 | J-pop |
| Ikimonogakari | Arigatou (ありがとう) | 2003 | J-pop |
| Ryokuoushoku Shakai | Hana ni Natte | 2020 | J-pop |
| Fujii Kaze | Shinunoga E-Wa | 2020 | J-pop |
| MOMOLAND | BBoom BBoom | 2018 | K-pop |
| Cowboy Bebop | Tank! | 1998 | Anime |
| Steins;Gate | Hacking the Gate | 2011 | Anime |
| Re:ZERO | Redo | 2016 | Anime |
| Fire Force | Inferno | 2019 | Anime |
| Carole and Tuesday | The Loneliest Girl | 2019 | Anime |
| Yu Peng Chen | Floating Life | 2020 | Genshin Impact |
| Yu Peng Chen | Caelestinum Finale Termini | 2020 | Genshin Impact |
| 星尘infinity | sword and snow | 2023 | Honkai Star Rail |
| Expedition 33 | Lumiere | 2024 | Game OST |

### Chinese/International Artists

| Artist | Song | Year | Notes |
|--------|------|------|-------|
| Zhou Shen | Big Fish (Da Yu) | 2016 | Reversed parser |
| Lexie Liu 刘柏辛 | 有吗炒面 | 2019 | CJK song name |
| Phoenix Legend | Fly Freely | 2005 | Chinese duo |
| Liu Huan | Night | 2009 | Chinese singer |
| Angela Zhang | Invisible Wings | 2006 | Taiwanese singer |
| Dimash Kudaibergen | SOS d'un terrien en détresse | 2017 | Kazakh vocalist |
| Beijing Welcomes You | Xiao Ke | 2008 | Chinese pop anthem |
| 縴夫的愛 [Boat Tracker Love] | 尹相杰、于文华 | 1993 | Chinese classic |
| 五十六个民族，五十六朵花 | (56 Ethnic groups, 56 flowers) | — | Chinese folk |
| Gong Xi Gong Xi | — | 1945 | Chinese New Year |
| Arash | Man O To | 2005 | Iranian-Swedish |

### Indie/Electronic/Gaming

| Artist | Song | Year | Notes |
|--------|------|------|-------|
| Poor Man's Poison | Hell's Coming With Me | 2015 | Indie folk |
| TheFatRat | Hunger | 2016 | Electronic |
| Set It Off | Partners In Crime | 2018 | ft. Ash Costello |
| Rodrigo y Gabriela | Hanuman | 2006 | Mexican guitar duo |
| Hooverphonics | Mad About You | 1996 | Belgian trip-hop |
| Leroy Anderson | Typewriter Symphony | 1950 | Orchestral classic |

## Still Unlabeled

### Real Songs (~120 remaining, mostly obscure indie)

These are genuine deep cuts — obscure indie artists, non-English tracks without
standard separators, custom arrangements, and personal playlist entries that
no API indexes. Highlights you might want to manually resolve:

| Rating | Title | Notes |
|--------|-------|-------|
| 91 | A song made entirely from videos that people sent via Twitter — Brett Domino | YouTube compilation |
| 84 | Funky Monday | Unknown artist |
| 84 | Chris Kazarian — How Good the Cold Feels | Indie |
| 84 | silvered heart – Morgan Reese | Indie |
| 84 | Lemonade – Thomas Stringfellow | Already resolved above |
| 84 | snow on the west coast – Hugo Santini | Indie |
| 82 | Dream Shadow – Big Problem | Indie |
| 82 | Malia Civets – Anybody But You | Indie |
| 80 | 【Lowland Jazz】純情スカート | Japanese brackets |
| 78 | heavy metal – Juxtaposition | Indie |
| 78 | cold heart – Sinatic | Indie |
| 78 | all my sleep – Nic Hanson | Indie |
| 78 | ayni Denizin Yuzune – Anadolu | Turkish |
| 65 | Summrs – Why Do U Lie 「 prod. Goyxrd 」 | Japanese quotes |
| 62 | "You'll Be There" by George Strait | Already resolved above |

### Meta/Review Entries (21 entries, no single year)

- Each Rating and a Sample song
- Rating System Update
- Double Review entries
- Musicord R10/R5/R3/R2 Reviews
- Rap/Hip hop Song Collection
- full country song list
- Curated Song Reviews
- "Contrast" pairs
- Collection of Lesser Represented Genres
- Various other review compilations
