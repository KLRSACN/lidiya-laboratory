def execute_write_text(packet):
    text=packet.get('payload',{}).get('text')
    if not isinstance(text,str): raise ValueError('text required')
    return text
