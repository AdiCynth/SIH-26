def summarize_orders(orders):
    total = 0
    count = 0
    for order in orders:
        total += order["amount"]
        count += 1
    average = total / count if count else 0
    return {"total": total, "count": count, "average": average}


def summarize_refunds(refunds):
    total = 0
    count = 0
    for order in refunds:
        total += order["amount"]
        count += 1
    average = total / count if count else 0
    return {"total": total, "count": count, "average": average}


def classify(value, mode, flag, extra):
    if mode == "a":
        if flag:
            if extra > 10:
                return "a-flag-high"
            elif extra > 5:
                return "a-flag-mid"
            else:
                return "a-flag-low"
        elif value > 100:
            return "a-big"
        else:
            return "a-small"
    elif mode == "b":
        if flag and extra:
            return "b-both"
        elif flag or extra:
            return "b-either"
        elif value < 0:
            return "b-negative"
        else:
            return "b-plain"
    elif mode == "c":
        return "c-high" if value > 50 else "c-low"
    return "unknown"
