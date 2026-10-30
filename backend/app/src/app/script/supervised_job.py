

import asyncio

from app import bgt
from app.agent.runtime import run_turn_with_retry
from app.agent.session import InMemorySessionRepository
from app.composition import build_embedding_page_retriever, build_model_client, build_tool_registry
from app.observability import setup_observability
from dotenv import load_dotenv


def main() -> None:

    load_dotenv()
    session_repository = InMemorySessionRepository()
    session = session_repository.create_session()
    document_retriever = build_embedding_page_retriever()
    setup_observability()

    def do_work() -> bool:
        """Run one turn of the agent with automatic retry on transient faults."""
        asyncio.run(run_turn_with_retry(
            session_id=session.session_id,
            user_text="create a note with Hello",
            model_client=build_model_client(),
            tool_registry=build_tool_registry(),
            session_repository=session_repository,
            document_retriever=document_retriever,
        ))
        return False  # Return False to stop after one run

    svc = bgt.SupervisedService.start(
        bgt.as_work_factory(do_work),
        name="example-thread",
        wakeup=bgt.IntervalOnlyWakeup(),  # only wake up on intervals
        interval=2,  # which are 2 seconds long
    )

    # asyncio.run(
    #     run_turn(
    #         session_id=session.session_id,
    #         user_text="create a note with Hello",
    #         model_client=build_model_client(),
    #         tool_registry=build_tool_registry(),
    #         session_repository=session_repository,
    #         document_retriever=document_retriever,
    #     )
    # )


if __name__ == "__main__":
    main()
