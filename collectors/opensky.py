from collectors.aviation import collect_aviation_signals


def collect_opensky_signals(*args, **kwargs):
    return collect_aviation_signals(*args, **kwargs)


if __name__ == "__main__":
    print(collect_opensky_signals())
