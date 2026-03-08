# fiyatlar.py
price_ranges = []

# 0-1000 arası 50'şer TL
for i in range(0, 1000, 50):
    price_ranges.append(f"{i}-{i+50}")

# 1000-5000 arası 250'şer TL
for i in range(1000, 5000, 250):
    price_ranges.append(f"{i}-{i+250}")

# 5000-20000 arası 1000'er TL
for i in range(5000, 20000, 1000):
    price_ranges.append(f"{i}-{i+1000}")

price_ranges.append("20000-1000000")