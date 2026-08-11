function latestUserModel(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const info = messages[index]?.info
    if (
      info?.role === "user" &&
      typeof info.model?.providerID === "string" &&
      info.model.providerID.length > 0 &&
      typeof info.model?.modelID === "string" &&
      info.model.modelID.length > 0
    ) {
      return {
        providerID: info.model.providerID,
        modelID: info.model.modelID,
        variant: info.variant ?? info.model.variant,
      }
    }
  }
  return undefined
}

export default async ({ client }) => ({
  config(config) {
    for (const agent of Object.values(config.agent ?? {})) {
      delete agent.model
    }
  },
  async "chat.message"(input, output) {
    const session = await client.session
      .get({ path: { id: input.sessionID } })
      .catch(() => undefined)
    const parentID = (session?.data ?? session)?.parentID
    if (typeof parentID !== "string" || parentID.length === 0) return

    const response = await client.session
      .messages({ path: { id: parentID } })
      .catch(() => undefined)
    const messages = response?.data ?? response
    const parentModel = latestUserModel(Array.isArray(messages) ? messages : [])
    if (!parentModel) return

    output.message.model = {
      providerID: parentModel.providerID,
      modelID: parentModel.modelID,
      ...(parentModel.variant === undefined ? {} : { variant: parentModel.variant }),
    }
    delete output.message.variant
  },
})
