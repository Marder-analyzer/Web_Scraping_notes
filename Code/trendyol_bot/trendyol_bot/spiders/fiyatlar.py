# fiyatlar.py
price_ranges = []

# 0-1000 arası 10'şer TL
for i in range(0, 1000, 10):
    price_ranges.append(f"{i}-{i+10}")

# 1000-5000 arası 20'şer TL
for i in range(1000, 5000, 20):
    price_ranges.append(f"{i}-{i+20}")

# 5000-20000 arası 50'er TL
for i in range(5000, 20000, 50):
    price_ranges.append(f"{i}-{i+50}")
    
# 20000-100000 arası 100'er TL
for i in range(20000, 100000, 100):
    price_ranges.append(f"{i}-{i+100}")

# 100000-500000 arası 1000'er TL
for i in range(100000, 500000, 1000):
    price_ranges.append(f"{i}-{i+1000}")

# 500000-5000000 arası 5000'er TL
for i in range(500000, 5000000, 5000):
    price_ranges.append(f"{i}-{i+5000}")

price_ranges.append("5000000-1000000000")