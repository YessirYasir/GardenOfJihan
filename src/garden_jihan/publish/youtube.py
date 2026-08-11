class PublishingNotConfigured(RuntimeError):
    pass


def publish_to_youtube(*_args, **_kwargs):
    raise PublishingNotConfigured(
        "YouTube publishing must use official OAuth and is not enabled in the early build."
    )
