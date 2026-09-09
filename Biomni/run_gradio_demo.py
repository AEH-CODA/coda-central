from biomni.agent import A1

agent = A1(path="./data", llm="nvidia/nemotron-3-super-120b-a12b", expected_data_lake_files=[])
agent.launch_gradio_demo(server_name="127.0.0.1")
