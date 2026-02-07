from http import cookies

import yt_dlp


url = input("Вставь ссылку на YouTube видео: ")


ydl_opts = {
    'js_runtime': 'node',  # указывает yt-dlp использовать Node.js
    'outtmpl': 'videos/%(title)s.%(ext)s',  # шаблон для имени файла
    'cookiefile': 'youtube.txt',  # путь к файлу с куки
    'format': 'bestvideo+bestaudio/best',  # выбирает лучшее видео и аудио,
    'merge_output_format': 'mp4',
    
    
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([url])
    
print("Готово ✅")
