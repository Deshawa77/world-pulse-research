from collectors.mobility import collect_mobility_signals, fetch_displacement_records


def collect_unhcr_signals(*args, **kwargs):
    return collect_mobility_signals(*args, **kwargs)


if __name__ == "__main__":
    print(collect_unhcr_signals())
