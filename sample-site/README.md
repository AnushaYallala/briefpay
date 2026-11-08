# Velugu Cove — Tourism Website

A small, mobile-friendly static website for **Velugu Cove**, a fictional coastal village in Andhra Pradesh, India. Built by freelancer **Arjun** for three local business owners who pooled resources through [BriefPay](https://github.com/AnushaYallala/briefpay).

## 🏖️ About

Three families run the heart of Velugu Cove's tourism:
- **Lakshmi** — Sea Breeze Homestay (rooms from ₹1,500/night)
- **Ravi** — Ravi's Fish Kitchen (legendary fish thali & seafood)
- **Meena** — Cove Boat Tours (sunset cruises, fishing trips, island hopping)

They needed a website to attract visitors. This is it.

## 📄 Pages

| Page | Description |
|---|---|
| `/` (Home) | Hero, "Why Visit" highlights, explore cards |
| `/stay` | Sea Breeze Homestay — rooms, pricing, amenities |
| `/eat` | Ravi's Fish Kitchen — menu, timings, location |
| `/tours` | Cove Boat Tours — tour types, schedule, safety |
| `/getting-there` | Directions from Visakhapatnam (air, train, road) |
| `/contact` | Enquiry form (name, interest, message) |

## 🛠️ Tech Stack

- Plain **HTML5 + CSS3 + vanilla JavaScript**
- No frameworks, no build tools, no dependencies
- Mobile-first responsive design
- Google Fonts (Poppins + Open Sans)

## 🚀 Running Locally

Just open `index.html` in a browser:
```bash
# Or use any static server:
python -m http.server 8080
npx serve .
```

## 📋 BRD Versions

This site has two tagged versions for the [BriefPay](https://github.com/AnushaYallala/briefpay) verification demo:

- **`v1-missing-form`** — All pages complete *except* the `/contact` enquiry form (404). The BriefPay Verification Agent marks this as **NEEDS_CHANGES**.
- **`v2-complete`** — The enquiry form is added. The Verification Agent marks this as **VERIFIED**.

## 📜 License

MIT
