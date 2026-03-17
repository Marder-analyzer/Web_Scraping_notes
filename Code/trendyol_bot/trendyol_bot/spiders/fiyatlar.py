# fiyatlar.py
price_ranges = []

# 0-1000 arası 50'şer TL
for i in range(0, 1000, 50):
    price_ranges.append(f"{i}-{i+50}")

# 1000-5000 arası 200'şer TL
for i in range(1000, 5000, 200):
    price_ranges.append(f"{i}-{i+200}")

# 5000-20000 arası 500'er TL
for i in range(5000, 10000, 500):
    price_ranges.append(f"{i}-{i+500}")

# 10000-20000 arası 1000'er TL
for i in range(10000, 20000, 1000):
    price_ranges.append(f"{i}-{i+1000}")
    
# 20000-100000 arası 2000'er TL
for i in range(20000, 100000, 2000):
    price_ranges.append(f"{i}-{i+2000}")

# 100000-500000 arası 10000'er TL
for i in range(100000, 500000, 10000):
    price_ranges.append(f"{i}-{i+10000}")

# 500000-5000000 arası 20000'er TL
for i in range(500000, 5000000, 20000):
    price_ranges.append(f"{i}-{i+20000}")

price_ranges.append("5000000-1000000000")