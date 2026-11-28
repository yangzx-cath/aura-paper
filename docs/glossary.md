# Glossary

## Nouns

| English | 中文 | Description |
| --- | --- | --- |
| `book` | 绘本 | One picture book PDF in the library |
| `source_page` | 源页 | One page as stored in the PDF |
| `page` | 书页 | One page as the reader sees it |
| `cover` | 封面 | The first page of a book |
| `breakdown` | 拆解表 | The text, panels, figures, and light of every page of a book |
| `panel` | 分格 | One rectangular picture area inside a page, holding a single moment of the story |
| `figure` | 形象 | One person, creature, or object drawn on a single page |
| `character` | 角色 | One role in the story, with a name, a look, and a voice that stay the same |
| `cast` | 阵容 | The full set of characters in a book |
| `location` | 场地 | One place where part of the story happens |
| `scene` | 场 | One continuous part of the story, in one place at one time |
| `shot` | 镜头 | One continuous camera view covering one or more panels, with its actions and spoken text |
| `line` | 台词 | One spoken sentence in a shot, dialogue or narration, paired with its speech audio |
| `track` | 音轨 | The timed audio of one shot |
| `manifest` | 镜头清单 | The full input of one video generation request |
| `clip` | 原片 | The raw video of one take, without the local audio |
| `take` | 镜次 | One generation attempt of a shot, with its clip and its track |
| `review` | 审片 | The quality check result of one take |
| `opening` | 片头 | The short video that opens a film, showing the book's title and style |
| `film` | 成片 | The finished video of a book |
| `subtitles` | 字幕 | The timed text of a film |

## Verbs

| English | 中文 | Description |
| --- | --- | --- |
| `ingest` | 入库 | Render the PDF into source pages, combine or split them into pages, and cut out the cover |
| `read` | 读页 | Read the cover and every page into one breakdown of text, panels, and figures |
| `crop` | 裁切 | Cut out the panel and figure images of each page and erase the printed text inside them |
| `cast` | 选角 | Group figures into characters, pick a reference image for each, and assign a voice |
| `scout` | 勘景 | Group panels into locations, pick a background image for each, and describe the art style |
| `identify` | 认人 | Match partly visible figures back to the characters they belong to |
| `direct` | 分镜 | Organize panels into scenes and shots, plan the actions, and assign the spoken lines |
| `record` | 配音 | Synthesize speech audio for every line and note its duration |
| `prepare` | 备料 | Build the timed track and the manifest of every shot |
| `render` | 生成 | Generate the raw clip of every shot from its manifest |
| `mix` | 混音 | Combine each raw clip with its track into one take |
| `audit` | 审片 | Check each take for audio and visual defects and give it a score |
| `assemble` | 合片 | Create the opening and join the chosen takes into the film |
| `subtitle` | 配字幕 | Align the lines to the film timeline and write the subtitle files |
