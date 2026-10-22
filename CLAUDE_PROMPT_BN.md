তুমি একজন সতর্ক Python engineer। এই project-এর `app.py` একটি Binance public-data Streamlit dashboard, paper-only trading prototype। নিম্নলিখিত কাজগুলো করো:
1. পুরো কোড রিভিউ করো এবং bug/security issue খুঁজে বের করো।
2. কোনো Binance API key, secret, wallet credential যোগ করবে না।
3. কোনো live order, withdrawal, leverage, futures বা real-money execution যোগ করবে না।
4. rate limit মেনে error handling, retry with backoff এবং cache যোগ করো।
5. paper trades, fees, cash balance ও position accounting-এর unit tests লেখো।
6. scanner-এর signals কীভাবে তৈরি হয় তা UI-তে ব্যাখ্যা করো।
7. Streamlit session reset limitation স্পষ্ট করে দেখাও।
8. পরিবর্তনের আগে আমাকে পরিকল্পনা দাও; বড় পরিবর্তনের আগে অনুমতি চাও।
9. সব tests চালাও এবং কোনগুলো সত্যিই pass হয়েছে তা বলো; না চালালে দাবি করবে না।
10. বাংলায় সহজ করে পরিবর্তনগুলো ব্যাখ্যা করো।
