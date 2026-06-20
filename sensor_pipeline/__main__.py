import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Sensor Community Kafka pipeline")
    parser.add_argument(
        "mode",
        choices=["bootstrap", "simulate", "produce", "consume"],
        help="bootstrap: seed profiles | simulate: emit MQTT | produce: MQTT→Kafka | consume: Kafka→S3",
    )
    args = parser.parse_args()

    if args.mode == "bootstrap":
        from sensor_pipeline.bootstrap import build_profiles
        build_profiles()
    elif args.mode == "simulate":
        from sensor_pipeline.simulator import run
        run()
    elif args.mode == "produce":
        from sensor_pipeline.producer import run
        run()
    elif args.mode == "consume":
        from sensor_pipeline.consumer import run
        run()


if __name__ == "__main__":
    main()
