namespace Unimarketing.UnimailApiSdk.CSharp.Model
{
    public class MessageSendRes
    {
        /// <summary>
        ///     信封ID(邮件发送ID)
        /// </summary>
        public long EnvelopeId { get; set; }

        /// <summary>
        ///     信封信息 url 相对路径
        /// </summary>
        public string EnvelopeIdLink { get; set; }

        /// <summary>
        ///     接收邮件地址
        /// </summary>
        public string Email { get; set; }

        /// <summary>
        ///     发送状态 queued：加入队列；deleted ：联系人被删除；invalided；联系人地址无效；unsubscribed；联系人已退订；blocked：不发送
        /// </summary>
        public string Status { get; set; }

        /// <summary>
        ///     不发送原因
        ///     recipientsQuotaReached：联系人已超过最大限制
        ///     messagesQuotaReached：邮件发送量已超过最大限制
        ///     messageSizeReached：邮件内容太大，超过64KB
        /// </summary>
        public string Warning { get; set; }

        /// <summary>
        ///     发送计划ID
        /// </summary>
        public long ScheduleId { get; set; }

        /// <summary>
        ///     发送计划信息url相对路径
        /// </summary>
        public string ScheduleIdLink { get; set; }

        /// <summary>
        ///     邮件ID
        /// </summary>
        public long MessageId { get; set; }

        /// <summary>
        ///     邮件信息url相对路径
        /// </summary>
        public string MessageIdLink { get; set; }

        public override string ToString()
        {
            return "EnvelopeId=" + EnvelopeId +
                   ",EnvelopeIdLink=" + EnvelopeIdLink +
                   ",Email=" + Email +
                   ",Status=" + Status +
                   ",Warning=" + Warning +
                   ",ScheduleId=" + ScheduleId +
                   ",ScheduleIdLink=" + ScheduleIdLink +
                   ",MessageId=" + MessageId +
                   ",MessageIdLink=" + MessageIdLink;
        }
    }
}