CREATE TABLE "ThreadLink" (
    "id" TEXT NOT NULL,
    "workspaceId" TEXT NOT NULL,
    "channelId" TEXT NOT NULL,
    "threadTs" TEXT NOT NULL,
    "jiraIssueKey" TEXT NOT NULL,
    "jiraIssueId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ThreadLink_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "ProcessedEvent" (
    "id" TEXT NOT NULL,
    "slackEventId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ProcessedEvent_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ThreadLink_workspaceId_channelId_threadTs_key" ON "ThreadLink"("workspaceId", "channelId", "threadTs");
CREATE UNIQUE INDEX "ProcessedEvent_slackEventId_key" ON "ProcessedEvent"("slackEventId");
