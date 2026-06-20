import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Sensor Community Kafka pipeline")
    parser.add_argument("mode", choices=["produce", "consume"], help="Run producer or consumer")
    args = parser.parse_args()

    if args.mode == "produce":
        from sensor_pipeline.producer import run
    else:
        from sensor_pipeline.consumer import run

    run()


if __name__ == "__main__":
    main()
