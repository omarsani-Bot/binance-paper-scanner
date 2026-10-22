# Binance Paper Scanner — বাংলা নির্দেশিকা

## এটি কী?
- Binance Spot-এর পাবলিক মার্কেট ডেটা ব্যবহার করে।
- ডিফল্টভাবে ৫৫টি উচ্চ quote-volume USDT spot market স্ক্যান করে।
- EMA(9)/EMA(21) crossover থেকে BUY/SELL/HOLD সিগন্যাল দেখায়।
- ম্যানুয়াল paper trading ও আনুমানিক fee হিসাব দেখায়।
- **কোনো API key নেই, কোনো real order পাঠায় না।**

## iPhone থেকে চালানোর সহজ পথ
iPhone-এ Python/Claude Code সরাসরি চালানো সবচেয়ে সহজ পথ নয়। ব্রাউজার-ভিত্তিক cloud development environment ব্যবহার করতে পারো, যেমন GitHub Codespaces (যদি তোমার অ্যাকাউন্টে উপলব্ধ থাকে) অথবা এমন Python hosting service যা Streamlit চালাতে পারে।

1. এই ZIP ফাইলটি ডাউনলোড করে Files অ্যাপে রাখো।
2. GitHub-এ সাইন ইন করে একটি নতুন private repository বানাও।
3. ZIP আনজিপ করে এর ফাইলগুলো repository-তে আপলোড করো (`app.py`, `requirements.txt`, `README_BN.md`, `CLAUDE_PROMPT_BN.md`)।
4. Codespaces চালু করো বা Streamlit সমর্থন করে এমন হোস্টিং বেছে নাও।
5. টার্মিনালে চালাও:
   ```bash
   python -m pip install -r requirements.txt
   streamlit run app.py --server.address 0.0.0.0 --server.port 8501
   ```
6. Codespaces হলে Ports ট্যাবে 8501 port-কে Open in Browser করো। অন্য hosting হলে তার নির্দেশনা অনুসরণ করো।
7. Dashboard-এ “Scan now” চাপো।

## Claude Code দিয়ে কাজ করাতে
Claude Code সাধারণত terminal-সহ development environment চায়। iPhone-এ সরাসরি সেটআপ জটিল হতে পারে; cloud terminal/Codespaces-এ Claude Code উপলব্ধ ও ইনস্টল করার অনুমতি থাকলে ব্যবহার করো। `CLAUDE_PROMPT_BN.md`-এর নির্দেশনা Claude Code-এ পেস্ট করো। Claude Code ইনস্টল করার আগে তার অফিসিয়াল বর্তমান নির্দেশনা দেখো।

## স্থানীয় কম্পিউটারে চালাতে
Python 3.11 বা 3.12 ইনস্টল করো। এরপর project folder-এ terminal খুলে:
```bash
python -m venv .venv
```
Windows:
```powershell
.venv\Scripts\Activate.ps1
```
macOS/Linux:
```bash
source .venv/bin/activate
```
তারপর:
```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## পরীক্ষা
1. প্রথমে 10 markets নির্বাচন করে Scan now চাপো।
2. এরপর 50 বা 55 markets নির্বাচন করো।
3. API/network error হলে কিছুক্ষণ পরে আবার চেষ্টা করো।
4. BUY signal থাকলে কেবল paper buy বোতাম দিয়ে simulation করো।
5. price change হলে আবার scan করে paper position-এর আনুমানিক P/L দেখো।
6. বাস্তব বাজারে কৌশল কার্যকর—এমন সিদ্ধান্ত নেয়ার আগে দীর্ঘ সময় ধরে paper test ও fee/slippage-aware backtest করো।

## সীমাবদ্ধতা
- EMA crossover কেবল উদাহরণভিত্তিক নিয়ম, AI prediction নয়।
- এই prototype প্রতিবার scan-এ candlestick request করে; 50+ symbol-এ ধীর হতে পারে এবং exchange rate limit/network সমস্যা হতে পারে।
- paper position ও history শুধু চলমান Streamlit session-এ থাকে; app restart করলে reset হবে।
- spread, slippage, partial fills, latency ও সব market constraints সম্পূর্ণ মডেল করা হয়নি।
- এটি কোনো লাভের নিশ্চয়তা দেয় না।
